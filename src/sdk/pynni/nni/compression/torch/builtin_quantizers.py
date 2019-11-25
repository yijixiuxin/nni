import logging
import torch
from .compressor import Quantizer

__all__ = ['NaiveQuantizer', 'QAT_Quantizer', 'DoReFaQuantizer']

logger = logging.getLogger(__name__)


class NaiveQuantizer(Quantizer):
    """quantize weight to 8 bits
    """
    def __init__(self, model, config_list):
        super().__init__(model, config_list)
        self.layer_scale = {}

    def quantize_weight(self, weight, config, op_name, **kwargs):
        new_scale = weight.abs().max() / 127
        scale = max(self.layer_scale.get(op_name, 0), new_scale)
        self.layer_scale[op_name] = scale
        orig_type = weight.type()  # TODO: user layer
        return weight.div(scale).type(torch.int8).type(orig_type).mul(scale)


def update_ema(biased_ema, value, decay, step):
    """
    calculate biased stat and unbiased stat in each step using exponential moving average method

    Parameters
    ----------
    biased_ema : float
        previous stat value
    value : float
        current stat value
    decay : float
        the weight of previous stat value, larger means smoother curve
    step : int
        current step

    Returns
    -------
    float, float
    """
    biased_ema = biased_ema * decay + (1 - decay) * value
    unbiased_ema = biased_ema / (1 - decay ** step)  # Bias correction
    return biased_ema, unbiased_ema

def update_quantization_param(bits, rmin, rmax):
    """
    calculate the `zero_point` and `scale`.

    Parameters
    ----------
    bits : int
        quantization bits length
    rmin : float
        min value of real value
    rmax : float
        max value of real value

    Returns
    -------
    float, float
    """
    # extend the [min, max] interval to ensure that it contains 0.
    # Otherwise, we would not meet the requirement that 0 be an exactly
    # representable value.
    rmin = min(rmin, 0)
    rmax = max(rmax, 0)

    # the min and max quantized values, as floating-point values
    qmin = 0
    qmax = (1 << bits) - 1
    # First determine the scale.
    scale = (rmax - rmin) / (qmax - qmin)

    # Zero-point computation.
    initial_zero_point = qmin - rmin / scale

    # Now we need to nudge the zero point to be an integer
    nudged_zero_point = 0
    if initial_zero_point < qmin:
        nudged_zero_point = qmin
    elif initial_zero_point > qmax:
        nudged_zero_point = qmax
    else:
        nudged_zero_point = torch.round(initial_zero_point)

    return scale, nudged_zero_point


def get_bits_length(config, quant_type):
    if isinstance(config["quant_bits"], int):
        return config["quant_bits"]
    else:
        return config["quant_bits"].get(quant_type)


class QAT_Quantizer(Quantizer):
    """Quantizer using the DoReFa scheme, as defined in:
    Quantization and Training of Neural Networks for Efficient Integer-Arithmetic-Only Inference
    http://openaccess.thecvf.com/content_cvpr_2018/papers/Jacob_Quantization_and_Training_CVPR_2018_paper.pdf
    """
    def __init__(self, model, config_list):
        """
        Parameters
        ----------
        layer : LayerInfo
            the layer to quantize
        config_list : list of dict
            list of configurations for quantization
            supported keys for dict:
                - quant_types : list of string
                    type of quantization you want to apply, currently support 'weight', 'input', 'output'
                - quant_bits : int or dict of {str : int}
                    bits length of quantization, key is the quantization type, value is the length, eg. {'weight', 8},
                    when the type is int, all quantization types share same bits length
                - quant_start_step : int
                    disable quantization until model are run by certain number of steps, this allows the network to enter a more stable
                    state where activation quantization ranges do not exclude a signiﬁcant fraction of values, default value is 0
                - op_types : list of string
                    types of nn.module you want to apply quantization, eg. 'Conv2d'
        """
        super().__init__(model, config_list)
        self.steps = 1
        modules_to_compress = self.detect_modules_to_compress()
        for layer, config in modules_to_compress:
            layer.module.register_buffer("zero_point", None)
            layer.module.register_buffer("scale", None)
            if "output" in config.get("quant_types", []):
                layer.module.register_buffer('ema_decay', torch.Tensor([0.99]))
                layer.module.register_buffer('tracked_min_biased', torch.zeros(1))
                layer.module.register_buffer('tracked_min', torch.zeros(1))
                layer.module.register_buffer('tracked_max_biased', torch.zeros(1))
                layer.module.register_buffer('tracked_max', torch.zeros(1))

    def _quantize(self, bits, op, real_val):
        """
        quantize real value.

        Parameters
        ----------
        bits : int
            quantization bits length
        op : torch.nn.module
            target module
        real_val : float
            real value to be quantized

        Returns
        -------
        float
        """
        transformed_val = op.zero_point + real_val / op.scale
        qmin = 0
        qmax = (1 << bits) - 1
        clamped_val = torch.clamp(transformed_val, qmin, qmax)
        quantized_val = torch.round(clamped_val)
        return quantized_val

    def _dequantize(self, op, quantized_val):
        """
        dequantize quantized value.
        Because we simulate quantization in training process, all the computations still happen as float point computations, which means we
        first quantize tensors then dequantize them. For more details, please refer to the paper.

        Parameters
        ----------
        op : torch.nn.Module
            target module
        quantized_val : float
            quantized_val value to be dequantized

        Returns
        -------
        float
        """
        real_val = op.scale * (quantized_val - op.zero_point)
        return real_val

    def quantize_weight(self, weight, config, op, **kwargs):
        weight_bits = get_bits_length(config, 'weight')
        quant_start_step = config.get('quant_start_step', 0)
        assert weight_bits >= 1, "quant bits length should be at least 1"

        if quant_start_step > self.steps:
            return weight
        rmin, rmax = torch.min(weight), torch.max(weight)
        op.scale, op.zero_point = update_quantization_param(weight_bits, rmin, rmax)
        out = self._quantize(weight_bits, op, weight)
        out = self._dequantize(op, out)
        return out

    def quantize_output(self, output, config, op, **kwargs):
        output_bits = get_bits_length(config, 'output')
        quant_start_step = config.get('quant_start_step', 0)
        assert output_bits >= 1, "quant bits length should be at least 1"

        if quant_start_step > self.steps:
            return output

        current_min, current_max = torch.min(output), torch.max(output)
        op.tracked_min_biased, op.tracked_min = update_ema(op.tracked_min_biased, current_min, op.ema_decay, self.steps)
        op.tracked_max_biased, op.tracked_max = update_ema(op.tracked_max_biased, current_max, op.ema_decay, self.steps)
        op.scale, op.zero_point = update_quantization_param(output_bits, op.tracked_min, op.tracked_max)
        out = self._quantize(output_bits, op, output)
        out = self._dequantize(op, out)
        return out

    def fold_bn(self, config, **kwargs):
        # TODO simulate folded weight
        pass

    def step(self):
        """
        override `compressor` `step` method, quantization only happens after certain number of steps
        """
        self.steps += 1


class DoReFaQuantizer(Quantizer):
    """Quantizer using the DoReFa scheme, as defined in:
    Zhou et al., DoReFa-Net: Training Low Bitwidth Convolutional Neural Networks with Low Bitwidth Gradients
    (https://arxiv.org/abs/1606.06160)
    """
    def __init__(self, model, config_list):
        """
        config_list: supported keys:
            - q_bits
        """
        super().__init__(model, config_list)

    def quantize_weight(self, weight, config, **kwargs):
        out = weight.tanh()
        out = out / (2 * out.abs().max()) + 0.5
        out = self.quantize(out, config['q_bits'])
        out = 2 * out -1
        return out

    def quantize(self, input_ri, q_bits):
        scale = pow(2, q_bits)-1
        output = torch.round(input_ri*scale)/scale
        return output