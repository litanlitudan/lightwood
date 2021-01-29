import torch
import torch.nn as nn
import numpy as np
from itertools import product
from lightwood.helpers.torch import LightwoodAutocast
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder


class DecoderRNNNumerical(nn.Module):
    def __init__(self, hidden_size, output_size):
        super(DecoderRNNNumerical, self).__init__()
        self.hidden_size = hidden_size
        self.in_activation = nn.Sigmoid()
        self.dropout = nn.Dropout(0.2)
        self.gru = nn.GRU(output_size, hidden_size, batch_first=True)
        self.out = nn.Linear(hidden_size, output_size)

    def forward(self, input, hidden):
        with LightwoodAutocast():
            output = self.in_activation(input.float())
            output, hidden = self.gru(output, hidden)
            output = self.dropout(output)
            output = self.out(output)
        return output, hidden

    def init_hidden(self, device, batch_size=1):
        return torch.zeros(1, batch_size, self.hidden_size, device=device)

    def decode(self, data, initial_tensor, criterion, device, hidden_state=None, sos=0):
        """This method decodes an input unrolled through time, given an initial hidden state"""
        if isinstance(data, tuple):
            # when using transformer encoder, data contains a sequence length tensor
            data, len_data = data

        if initial_tensor.shape[1] > 1:
            # if tensor is a sequence (like the one yielded by the transformer),
            # we select only the last timestep for decoding
            initial_tensor = initial_tensor[:, -1:, :]

        loss = 0
        next_tensor = torch.full_like(initial_tensor, sos, dtype=torch.float32).to(device)
        tensor_target = torch.cat([next_tensor, data], dim=1)  # add SOS token at t=0 to true input
        if hidden_state is None:
            hidden_state = self.init_hidden(device, data.shape[0])

        for tensor_i in range(data.shape[1] - 1):
            rand = np.random.randint(2)
            # teach from forward as well as from known tensor alternatively
            if rand == 1:
                next_tensor, hidden_state = self.forward(tensor_target[:, tensor_i, :].unsqueeze(dim=1), hidden_state)
            else:
                next_tensor, hidden_state = self.forward(next_tensor.detach(), hidden_state)

            loss += criterion(next_tensor, tensor_target[:, tensor_i + 1, :].unsqueeze(dim=1))

        return next_tensor, hidden_state, loss


class EncoderRNNNumerical(nn.Module):
    def __init__(self,  input_size, hidden_size):
        super(EncoderRNNNumerical, self).__init__()
        self.hidden_size = hidden_size
        self.dropout = nn.Dropout(0.2)
        self.gru = nn.GRU(input_size, hidden_size, batch_first=True)
        self.out = nn.Linear(hidden_size, input_size)

    def forward(self, input, hidden):
        with LightwoodAutocast():
            output, hidden = self.gru(input, hidden)
            output = self.dropout(output)
            output = self.out(output)
        return output, hidden

    def init_hidden(self, device, batch_size=1):
        return torch.zeros(1, batch_size, self.hidden_size, device=device)

    def bptt(self, data, criterion, device):
        """This method encodes an input unrolled through time"""
        loss = 0
        hidden_state = self.init_hidden(device, batch_size=data.shape[0])
        next_tensor = data[:, 0, :].unsqueeze(dim=1)  # initial input

        for tensor_i in range(data.shape[1] - 1):
            rand = np.random.randint(2)
            # teach from forward as well as from known tensor alternatively
            if rand == 1:
                next_tensor, hidden_state = self.forward(data[:, tensor_i, :].unsqueeze(dim=1), hidden_state)
            else:
                next_tensor, hidden_state = self.forward(next_tensor.detach(), hidden_state)

            loss += criterion(next_tensor, data[:, tensor_i + 1, :].unsqueeze(dim=1))

        return next_tensor, hidden_state, loss


class MinMaxNormalizer:
    def __init__(self, combination=[], keys=[], factor=1):
        self.scaler = MinMaxScaler()
        self.factor = factor
        self.keys = list(keys)  # columns involved in grouped-by subset dataset to normalize
        self.combination = combination  # tuple with values in those columns
        self.abs_mean = None

    def prepare(self, x):
        X = np.array([j for i in x for j in i]).reshape(-1, 1) if isinstance(x, list) else x
        X[X == None] = 0
        self.abs_mean = np.mean(np.abs(X))
        self.scaler.fit(X)

    def encode(self, y):
        if not isinstance(y, np.ndarray) and not isinstance(y[0], list):
            y = y.reshape(-1, 1)
        return torch.Tensor(self.scaler.transform(y))

    def decode(self, y):
        return self.scaler.inverse_transform(y)


class CatNormalizer:
    def __init__(self):
        self.scaler = OneHotEncoder(sparse=False, handle_unknown='ignore')
        self.unk = "<UNK>"

    def prepare(self, x):
        X = []
        for i in x:
            for j in i:
                X.append(j if j is not None else self.unk)
        self.scaler.fit(np.array(X).reshape(-1, 1))

    def encode(self, Y):
        y = np.array([[j if j is not None else self.unk for j in i] for i in Y])
        out = []
        for i in y:
            out.append(self.scaler.transform(i.reshape(-1, 1)))
        return torch.Tensor(out)

    def decode(self, y):
        return [[i[0] for i in self.scaler.inverse_transform(o)] for o in y]


def get_group_matches(data, combination, keys):
    """Given a grouped-by combination, return rows of the data that match belong to it. Params:
    data: dict with data to filter and group-by columns info.
    combination: tuple with values to filter by
    keys: which column does each combination value belong to

    return: indexes for rows to normalize, data to normalize
    """
    all_sets = []
    for val, key in zip(combination, keys):
        all_sets.append(set([i for i, elt in enumerate(data['group_info'][key]) if elt == val]))
    if all_sets:
        idxs = list(set.intersection(*all_sets))
        return idxs, np.array(data['data'])[idxs, :]
    else:
        return [], np.array([])


def generate_target_group_normalizers(data):
    """
    Helper function called from data_source. It generates and fits all needed normalizers for a target variable
    based on its grouped entities.
    :param data:
    :return: modified data with dictionary with normalizers for said target variable based on some grouped-by columns
    """
    normalizers = {}
    group_combinations = ['__default']

    # todo in rnn self._target_ar_normalizers[data['name']] = {}

    # categorical normalizers
    if data['original_type'] == 'categorical':
        normalizers['__default'] = CatNormalizer()
        normalizers['__default'].prepare(data['data'])

    # numerical normalizers, here we spawn one per each group combination
    else:
        group_combinations.extend(list(product(*[set(x) for x in data['group_info'].values()])))
        for combination in group_combinations:
            combination = frozenset(combination)  # freeze so that we can hash with it
            _, subset = get_group_matches(data, combination, data['group_info'].keys())
            if subset.size > 0:
                normalizers[combination] = MinMaxNormalizer(combination=combination, keys=data['group_info'].keys())
                normalizers[combination].prepare(subset)

        # ...plus a default one, used at inference time and fitted with all training data
        normalizers['__default'] = MinMaxNormalizer()
        normalizers['__default'].prepare(data['data'])

    data['normalizers'] = normalizers
    data['group_combinations'] = group_combinations

    return data
