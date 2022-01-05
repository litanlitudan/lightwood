from typing import List, Optional

import torch
from torch import nn
from torch.optim import SGD

from lightwood.mixer.base import BaseMixer
from lightwood.ensemble.stacked_ensemble import StackedEnsemble
from lightwood.encoder.numeric.ts_array_numeric import TsArrayNumericEncoder
from lightwood.api.types import PredictionArguments
from lightwood.data.encoded_ds import EncodedDs
from lightwood.helpers.log import log


class TsStackedEnsemble(StackedEnsemble):
    def __init__(self, target, mixers: List[BaseMixer], data: EncodedDs, dtype_dict: dict, horizon: int,
                 pred_args: PredictionArguments, fit: Optional[bool] = True) -> None:
        super().__init__(target, mixers, data, dtype_dict, pred_args, fit=False)
        if not isinstance(data.encoders[target], TsArrayNumericEncoder):
            raise Exception('This ensemble can only be used to forecast!')

        self.horizon = horizon
        self.target_cols = [target] + [f'{target}_timestep_{t+1}' for t in range(self.horizon - 1)]
        self.agg_dim = 2

        if fit:
            all_preds = torch.tensor(self.predict(data, pred_args)).squeeze().reshape(-1, self.horizon, len(mixers))
            actual = torch.tensor(data.data_frame[self.target_cols].values)
            nan_mask = actual != actual
            actual[nan_mask] = 0
            all_preds[nan_mask] = 0

            criterion = nn.MSELoss()
            optimizer = SGD([self.mixer_weights], lr=0.01)

            def _eval_loss():
                optimizer.zero_grad()
                weighted = torch.sum(all_preds * self.softmax(self.mixer_weights), dim=2)
                loss = criterion(weighted, actual)
                loss.backward()
                return loss

            optimizer.step(_eval_loss)
            self.mixer_weights = self.softmax(self.mixer_weights)
            log.info(f'Optimal stacking weights: {self.mixer_weights.detach().tolist()}')
            self.prepared = True
