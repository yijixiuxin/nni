Exploration Strategy
====================

There are two types of model space exploration approach: **Multi-trial strategy** and **One-shot strategy**. When the model space has been constructed, users can use either exploration approach to explore the model space. 

* :ref:`Mutli-trial strategy <multi-trial-nas>` trains each sampled model in the model space independently.
* :ref:`One-shot strategy <one-shot-nas>` samples the model from a super model.

Here is the list of exploration strategies that NNI has supported.

.. list-table::
   :header-rows: 1
   :widths: auto

   * - Name
     - Category
     - Brief Description
   * - :class:`Random <nni.retiarii.strategy.Random>`
     - :ref:`Multi-trial <multi-trial-nas>`
     - Randomly sample an architecture each time
   * - :class:`GridSearch <nni.retiarii.strategy.GridSearch>`
     - :ref:`Multi-trial <multi-trial-nas>`
     - Traverse the search space and try all possibilities
   * - :class:`RegularizedEvolution <nni.retiarii.strategy.RegularizedEvolution>`
     - :ref:`Multi-trial <multi-trial-nas>`
     - Evolution algorithm for NAS. `Reference <https://arxiv.org/abs/1802.01548>`__
   * - :class:`TPE <nni.retiarii.strategy.TPE>`
     - :ref:`Multi-trial <multi-trial-nas>`
     - Tree-structured Parzen Estimator (TPE). `Reference <https://papers.nips.cc/paper/4443-algorithms-for-hyper-parameter-optimization.pdf>`__
   * - :class:`PolicyBasedRL <nni.retiarii.strategy.PolicyBasedRL>`
     - :ref:`Multi-trial <multi-trial-nas>`
     - Policy-based reinforcement learning, based on implementation of tianshou. `Reference <https://arxiv.org/abs/1611.01578>`__
   * - :class:`DARTS <nni.retiarii.strategy.DARTS>`
     - :ref:`One-shot <one-shot-nas>`
     - Continuous relaxation of the architecture representation, allowing efficient search of the architecture using gradient descent. `Reference <https://arxiv.org/abs/1806.09055>`__
   * - :class:`ENAS <nni.retiarii.strategy.ENAS>`
     - :ref:`One-shot <one-shot-nas>`
     - RL controller learns to generate the best network on a super-net. `Reference <https://arxiv.org/abs/1802.03268>`__
   * - :class:`GumbelDARTS <nni.retiarii.strategy.GumbelDARTS>`
     - :ref:`One-shot <one-shot-nas>`
     - Choose the best block by using Gumbel Softmax random sampling and differentiable training. `Reference <https://arxiv.org/abs/1812.03443>`__
   * - :class:`RandomOneShot <nni.retiarii.strategy.RandomOneShot>`
     - :ref:`One-shot <one-shot-nas>`
     - Train a super-net with uniform path sampling. `Reference <https://arxiv.org/abs/1904.00420>`__
   * - :class:`Proxyless <nni.retiarii.strategy.Proxyless>`
     - :ref:`One-shot <one-shot-nas>`
     - A low-memory-consuming optimized version of differentiable architecture search. `Reference <https://arxiv.org/abs/1812.00332>`__

.. _multi-trial-nas:

Multi-trial strategy
--------------------

Multi-trial NAS means each sampled model from model space is trained independently. A typical multi-trial NAS is `NASNet <https://arxiv.org/abs/1707.07012>`__. In multi-trial NAS, users need model evaluator to evaluate the performance of each sampled model, and need an exploration strategy to sample models from a defined model space. Here, users could use NNI provided model evaluators or write their own model evalutor. They can simply choose a exploration strategy. Advanced users can also customize new exploration strategy.

To use an exploration strategy, users simply instantiate an exploration strategy and pass the instantiated object to :class:`~nni.retiarii.experiment.pytorch.RetiariiExperiment`. Below is a simple example.

.. code-block:: python

   import nni.retiarii.strategy as strategy
   exploration_strategy = strategy.Random(dedup=True)

Rather than using :class:`strategy.Random <nni.retiarii.strategy.Random>`, users can choose one of the strategies from the table above.

.. _one-shot-nas:

One-shot strategy
-----------------

One-shot NAS algorithms leverage weight sharing among models in neural architecture search space to train a supernet, and use this supernet to guide the selection of better models. This type of algorihtms greatly reduces computational resource compared to independently training each model from scratch (which we call "Multi-trial NAS").

Starting from v2.8, the usage of one-shot strategies are much alike to multi-trial strategies. Users simply need to create a strategy and run :class:`~nni.retiarii.experiment.pytorch.RetiariiExperiment`. Since one-shot strategies will manipulate the training recipe, to use a one-shot strategy, the evaluator needs to be one of the :ref:`PyTorch-Lightning evaluators <lightning-evaluator>`, either built-in or customized. Last but not least, don't forget to set execution engine to ``oneshot``. Example follows:

.. code-block:: python

   import nni.retiarii.strategy as strategy
   import nni.retiarii.evaluator.pytorch.lightning as pl
   evaluator = pl.Classification(
     # Need to use `pl.DataLoader` instead of `torch.utils.data.DataLoader` here,
     # or use `nni.trace` to wrap `torch.utils.data.DataLoader`.
     train_dataloaders=pl.DataLoader(train_dataset, batch_size=100),
     val_dataloaders=pl.DataLoader(test_dataset, batch_size=100),
     # Other keyword arguments passed to pytorch_lightning.Trainer.
     max_epochs=10,
     gpus=1,
   )
   exploration_strategy = strategy.DARTS()

   exp_config.execution_engine = 'oneshot'

One-shot strategies only support a limited set of mutation primitives, and does not support :doc:`customizing mutators <mutator>` at all. See the :doc:`reference </reference/nas>` for the detailed support list of each algorithm.

.. versionadded:: 2.8

   One-shot strategy is now compatible with `Lightning accelerators <https://pytorch-lightning.readthedocs.io/en/stable/accelerators/gpu.html>`__. It means that, you can accelerate one-shot strategies on hardwares like multiple GPUs. To enable this feature, you only need to pass the keyword arguments which used to be set in ``pytorch_lightning.Trainer``, to your evaluator. See :doc:`this reference </reference/nas>` for more details.
