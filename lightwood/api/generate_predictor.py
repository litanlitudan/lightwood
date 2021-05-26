import lightwood
from lightwood.api import LightwoodConfig
from mindsdb_datasources import DataSource


def generate_predictor_code(lightwood_config: LightwoodConfig) -> str:
    feature_code_arr = []
    for feature in lightwood_config.features.values():
        feature_code_arr.append(f"""'{feature.name}': {feature.encoder}""")

    encoder_code = '{\n            ' + ',\n            '.join(feature_code_arr) + '\n        }'
    import_code = '\n'.join(lightwood_config.imports)

    return f"""{import_code}
import pandas as pd
from mindsdb_datasources import DataSource
from lightwood.helpers.seed import seed
from lightwood.helpers.log import log
import lightwood


class Predictor():
    def __init__(self):
        seed()
        self.target = '{lightwood_config.output.name}'

    def learn(self, data: DataSource) -> None:
        # Build a Graph from the JSON
        # Using eval is a bit ugly and we could replace it with factories, personally I'm against this, as it ads pointless complexity
        self.encoders = {encoder_code}

        log.info('Cleaning up, transforming and splitting the data')
        data = {lightwood_config.cleaner}(data)
        folds = {lightwood_config.splitter}(data, 10)
        nfolds = len(data)

        log.info('Training the encoders')
        for col_name, encoder in self.encoders.items():
            if encoder.uses_folds:
                encoder.prepare([x[col_name] for x in folds[0:nfolds]])
            else:
                encoder.prepare(pd.concat(folds[0:nfolds])[col_name])

        log.info('Featurizing the data')
        encoded_ds_arr = lightwood.encode(self.encoders, folds, self.target)

        log.info('Training the models')
        self.models = {lightwood_config.output.models}
        for model in self.models:
            model.fit(encoded_ds_arr[0:nfolds], folds[0:nfolds])

        log.info('Ensembling the model')
        self.ensemble = {lightwood_config.output.ensemble}(self.models, encoded_ds_arr[nfolds], data[nfolds])

        log.info('Analyzing the ensemble')
        # Add back when analysis works
        # self.confidence_model, self.predictor_analysis = {lightwood_config.analyzer}(self.ensemble, encoded_ds_arr[nfolds], data[nfolds])

    def predict(self, data: DataSource) -> pd.DataFrame:
        encoded_ds_arr = lightwood.encode(self.encoders, data)
        df = self.ensemble(encoded_ds_arr)
        return df

"""


def config_from_data(target: str, data: DataSource) -> None:
    type_information = lightwood.data.infer_types(data)
    statistical_analysis = lightwood.data.statistical_analysis(data, type_information)
    lightwood_config = lightwood.generate_config(target, type_information=type_information, statistical_analysis=statistical_analysis)
    return lightwood_config


def generate_predictor(target: str = None, datasource: DataSource = None, lightwood_config: LightwoodConfig = None) -> str:
    if lightwood_config is None:
        lightwood_config = config_from_data(target, datasource)

    predictor_code = generate_predictor_code(lightwood_config)
    return predictor_code
