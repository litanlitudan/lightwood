import unittest

import torch

from lightwood.helpers.device import get_devices
from lightwood.encoders.time_series import RnnEncoder
from lightwood.encoders.time_series.helpers.rnn_helpers import *


class TestRnnEncoder(unittest.TestCase):

    def test_padding(self):
        series = [['1', '2', '3 '], ['2', '3'], ['3', '4', '5', '6'], [' 4', '5', '6']]
        target = [[1.0, 2.0, 3.0, 4.0, 0.0], [2.0, 3.0, 4.0, 5.0, 0.0], [3.0, 0.0, 5.0, 6.0, 0.0]]
        result = tensor_from_series(series, get_devices()[0], n_dims=5, pad_value=0.0, max_len=3).tolist()[0]
        self.assertEqual(result, target)

    def test_normalizer(self):
        data = [[-100.0, -5.0, 0.0, 5.0, 100.0],
                [-1000.0, -50.0, 0.0, 50.0, 1000.0],
                [-500.0, -405.0, -400.0, -395.0, -300.0],
                [300.0, 395.0, 400.0, 405.0, 500.0],
                [0.0, 1e3, 1e6, 1e9, 1e12]]
        normalizer = TanhNormalizer()
        reconstructed = normalizer.inverse_transform(normalizer.fit_transform(data))
        self.assertTrue(np.allclose(data, reconstructed, atol=0.1))

    def test_overfit_singledimensional(self):
        series = ['1 2 3 4 5', '2 3 4 5 6', '3 4 5 6 7', '4 5 6 7 8']  # format given by native
        data = series * 20
        batch_size = 1
        timesteps = 5
        n_dims = 1

        encoder = RnnEncoder(encoded_vector_size=10, train_iters=50, ts_n_dims=n_dims)
        encoder.prepare_encoder(data, feedback_hoop_function=lambda x: print(x), batch_size=batch_size)
        encoded = encoder.encode(data)
        decoded = encoder.decode(encoded, steps=timesteps).tolist()

        unequal = 0
        equal = 0
        data = float_matrix_from_strlist(data)

        # [print([round(dd,2) for dd in d]) for d in decoded]
        # [print(d) for d in data]

        self.assertEqual(len(data), len(decoded))
        self.assertEqual(len(data[0]), len(decoded[0]))
        for i in range(len(data)):
            for n in range(timesteps):
                if int(decoded[i][n]) == int(data[i][n]):
                    equal += 1
                else:
                    unequal += 1

        print(f'Decoder got {equal} correct and {unequal} incorrect')
        # Not much else we can do here, trains slowly, it's the nature of the type of network and travis is really slow
        self.assertGreater(equal, unequal)

        query = ['1 2 3', '2 3 4', '3 4 5', '4 5 6']
        answer = [4, 5, 6, 7]
        error_margin = 2
        encoded_data, preds = encoder.encode(query, get_next_count=1)
        decoded_data = encoder.decode(encoded_data, steps=4).tolist()

        # check prediction
        preds = preds.squeeze().tolist()

        for ans, pred in zip(answer, preds):
            self.assertGreater(error_margin, abs(pred - ans))

        # check reconstruction
        float_query = float_matrix_from_strlist(query)

        for qry, dec in zip(float_query, decoded_data):
            for truth, pred in zip(qry, dec):
                self.assertGreater(error_margin, abs(truth - pred))

    def test_overfit_multidimensional(self):
        pass
        # series = [[['1', '2', '3', '4', '5', '6'], ['2', '3', '4', '5', '6', '7'],
        #            ['3', '4', '5', '6', '7', '8'], ['4', '5', '6', '7', '8', '9']]]
        # data = series * 20
        # n_dims = max([len(q) for q in data])
        # timesteps = max([len(q[0]) for q in data])
        # batch_size = 1

        # encoder = RnnEncoder(encoded_vector_size=10, train_iters=400, ts_n_dims=n_dims)
        # encoder.prepare_encoder(data, feedback_hoop_function=lambda x: print(x), batch_size=batch_size)
        # encoded = encoder.encode(data)
        # decoded = encoder.decode(encoded, steps=timesteps)
        # equal = 0
        # unequal = 0
        # self.assertEqual(len(data), len(decoded))
        # self.assertEqual(len(data[0]), len(decoded[0]))
        # for i in range(len(data[0])):
        #     self.assertEqual(len(data[0][i]), len(decoded[0][i]))
        #     for n in range(len(data[0][i])):
        #         if int(decoded[0][i][n]) == int(data[0][i][n]):
        #             equal += 1
        #         else:
        #             unequal += 1
        # print(f'Decoder got {equal} correct and {unequal} incorrect')
        # # Not much else we can do here, trains slowly, it's the nature of the type of network and travis is really slow
        # self.assertGreater(equal, unequal)
        # query = [[['1', '2', '3'], ['2', '3', '4'], ['3', '4', '5'], ['4', '5', '6']]]
        # answer = [4, 5, 6, 7]
        # error_margin = 1
        # encoded_data, preds = encoder.encode(query, get_next_count=1)
        # decoded_data = encoder.decode(encoded_data, steps=len(query[0][0])).tolist()
        # # check prediction
        # preds = torch.reshape(preds, (1, n_dims)).tolist()[-1]
        # for ans, pred in zip(answer, preds):
        #     self.assertGreater(error_margin, abs(pred - ans))
        # # check reconstruction
        # float_query = [list(map(float, q)) for q in query[0]]
        # for qry, dec in zip(float_query, decoded_data[0]):
        #     for truth, pred in zip(qry, dec):
        #         self.assertGreater(error_margin, abs(truth - pred))
