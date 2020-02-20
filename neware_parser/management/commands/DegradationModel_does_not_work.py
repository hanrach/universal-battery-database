import tensorflow as tf

from tensorflow.keras import Model
from tensorflow.keras.layers import Dense, Layer

from .colour_print import Print

class FeedforwardNeuralNetwork:
    def __init__(self, depth, width):
        self.initial = Dense(
            width,
            activation = 'relu',
            use_bias = True,
            bias_initializer = 'zeros'
        )

        self.bulk = [
            Dense(
                width,
                activation = 'relu',
                use_bias = True,
                bias_initializer = 'zeros'
            ) for _ in range(depth)
        ]

        self.final = Dense(
            1,
            activation = None,
            use_bias = True,
            bias_initializer = 'zeros',
            kernel_initializer = 'zeros'
        )

class DegradationModel(Model):

    def __init__(self, num_keys, depth, width):
        super(DegradationModel, self).__init__()

        self.nn_cap = FeedforwardNeuralNetwork(depth, width)
        self.nn_eq_vol = FeedforwardNeuralNetwork(depth, width)
        self.nn_r = FeedforwardNeuralNetwork(depth, width)

        self.nn_theoretical_cap = FeedforwardNeuralNetwork(depth, width)
        self.nn_soc = FeedforwardNeuralNetwork(depth, width)
        self.nn_soc_0 = FeedforwardNeuralNetwork(depth, width)
        self.nn_init_soc = FeedforwardNeuralNetwork(depth, width)

        self.dictionary = DictionaryLayer(num_features=width, num_keys=num_keys)

        self.width = width
        self.num_keys = num_keys

    # Begin: nn application functions ==========================================

    def norm_cycle(self, params):
        return params["cycles"]

    def cell_feat(self, params):
        return params["features"]

    def norm_cycle_flat(self, params):
        return (
            params["cycles_flat"]
            * (1e-10 + tf.exp(-params["features_flat"][:, 0:1]))
        )

    def cell_feat_flat(self, params):
        return params["features_flat"][:, 1:]

    # Structured variables -----------------------------------------------------

    def max_dchg_vol(self, params):
        eq_vol = self.eq_vol(params)
        r = self.r(params)

        return eq_vol - (params["dchg_rate"] * r)

    # Unstructured variables ---------------------------------------------------

    def cap(self, params):
        Print.colour(Print.BLUE, "initial")
        Print.colour(Print.RED, self.nn_cap.initial)
        centers = self.nn_cap.initial(
            tf.concat(
                (
                    self.norm_cycle_flat(params),
                    params["rates_flat"],
                    self.cell_feat_flat(params)
                ),
                axis=1
            )
        )
        Print.colour(Print.BLUE, "bulk")
        Print.colour(Print.RED, self.nn_cap.bulk)
        for d in self.nn_cap.bulk:
            centers = d(centers)
        Print.colour(Print.BLUE, "final")
        Print.colour(Print.RED, self.nn_cap.final)
        return self.nn_cap.final(centers)

    def eq_vol(self, params):
        centers = self.nn_eq_vol.initial(
            tf.concat(
                (
                    self.norm_cycle(params),
                    params["chg_rate"],
                    self.cell_feat(params)
                ),
                axis=1
            )
        )
        for d in self.nn_eq_vol.bulk:
            centers = d(centers)
        return self.nn_eq_vol.final(centers)

    def r(self, params):
        centers = self.nn_r.initial(
            tf.concat(
                (
                    self.norm_cycle(params),
                    self.cell_feat(params)
                ),
                axis=1
            )
        )
        for d in self.nn_r.bulk:
            centers = d(centers)
        return self.nn_r.final(centers)

    # End: nn application functions ============================================

    def create_derivatives(self, params, nn):
        derivatives = {}

        with tf.GradientTape(persistent=True) as tape3:
            tape3.watch(params)

            with tf.GradientTape(persistent=True) as tape2:
                tape2.watch(params)

                res = tf.reshape(nn(params), [-1, 1])

            # NOTE: why do some have `[:, 0, :]` and others don't?
            derivatives['dCyc'] = tape2.batch_jacobian(
                source=params["cycles"],
                target=res
            )[:, 0, :]
            derivatives['d_chg_rate'] = tape2.batch_jacobian(
                source=params["chg_rate"],
                target=res
            )[:, 0, :]
            derivatives['d_dchg_rate'] = tape2.batch_jacobian(
                source=params["dchg_rate"],
                target=res
            )[:, 0, :]
            derivatives['dFeatures'] = tape2.batch_jacobian(
                source=params["features"],
                target=res
            )[:, 0, :]
            del tape2

        derivatives['d2Cyc'] = tape3.batch_jacobian(
            source=params["cycles"],
            target=derivatives['dCyc']
        )[:, 0, :]
        derivatives['d2_chg_rate'] = tape3.batch_jacobian(
            source=params["chg_rate"],
            target=derivatives['d_chg_rate']
        )
        derivatives['d2_dchg_rate'] = tape3.batch_jacobian(
            source=params["dchg_rate"],
            target=derivatives['d_dchg_rate']
        )
        derivatives['d2Features'] = tape3.batch_jacobian(
            source=params["features"],
            target=derivatives['dFeatures']
        )

        del tape3
        return res, derivatives

    def create_derivatives_flat(self, params, nn):
        derivatives = {}

        with tf.GradientTape(persistent=True) as tape3:
            tape3.watch(params)

            with tf.GradientTape(persistent=True) as tape2:
                tape2.watch(params)

                res = tf.reshape(nn(params), [-1, 1])

            derivatives['dCyc'] = tape2.batch_jacobian(
                source=params["cycles_flat"],
                target=res
            )[:, 0, :]
            derivatives['dRates'] = tape2.batch_jacobian(
                source=params["rates_flat"],
                target=res
            )[:, 0, :]
            derivatives['dFeatures'] = tape2.batch_jacobian(
                source=params["features_flat"],
                target=res
            )[:, 0, :]
            del tape2

        derivatives['d2Cyc'] = tape3.batch_jacobian(
            source=params["cycles_flat"],
            target=derivatives['dCyc']
        )[:, 0, :]
        derivatives['d2Rates'] = tape3.batch_jacobian(
            source=params["rates_flat"],
            target=derivatives['dRates']
        )
        derivatives['d2Features'] = tape3.batch_jacobian(
            source=params["features_flat"],
            target=derivatives['dFeatures']
        )

        del tape3
        return res, derivatives

    def call(self, x, training=False):

        centers = x[0]  # batch of [cyc, k[0], k[1]]
        indecies = x[1]  # batch of index
        meas_cycles = x[2]  # batch of cycles
        vol_tensor = x[3]

        features, mean, log_sig = self.dictionary(indecies, training=training)
        cycles = centers[:, 0:1]
        rates = centers[:, 1:]

        # duplicate cycles and others for all the voltages
        # dimensions are now [batch, voltages, features]
        cycles_tiled = tf.tile(
            tf.expand_dims(cycles, axis=1),
            [1, vol_tensor.shape[0], 1]
        )
        rates_tiled = tf.tile(
            tf.expand_dims(rates, axis=1),
            [1, vol_tensor.shape[0], 1]
        )
        features_tiled = tf.tile(
            tf.expand_dims(features, axis=1),
            [1, vol_tensor.shape[0], 1]
        )
        voltages_tiled = tf.tile(
            tf.expand_dims(tf.expand_dims(vol_tensor, axis=1), axis=0),
            [cycles.shape[0], 1, 1]
        )

        # TODO wtf does rates_concat contain dchg_rate, chg_rate, and voltage?!
        rates_concat = tf.concat((rates_tiled, voltages_tiled), axis=2)

        params = {
            "cycles_flat": tf.reshape(cycles_tiled, [-1, 1]),
            "rates_flat": tf.reshape(rates_concat, [-1, 3]),
            "features_flat": tf.reshape(features_tiled, [-1, self.width]),

            # TODO is this correct?!
            "cycles": cycles * (1e-10 + tf.exp(-features[:, 0:1])),
            "chg_rate": rates[:, 0:1],
            "dchg_rate": rates[:, 1:2],
            "features": features[:, 1:]
        }

        if training:

            var_cyc = tf.expand_dims(meas_cycles, axis=1) - cycles
            var_cyc_squared = tf.square(var_cyc)

            ''' discharge capacity '''
            cap, cap_der = self.create_derivatives_flat(params, self.cap)
            cap = tf.reshape(cap, [-1, vol_tensor.shape[0]])

            pred_cap = (
                cap + var_cyc * tf.reshape(
                    cap_der['dCyc'], [-1, vol_tensor.shape[0]])
                + var_cyc_squared * tf.reshape(
                    cap_der['d2Cyc'], [-1, vol_tensor.shape[0]])
            )

            ''' discharge max voltage '''
            max_dchg_vol, max_dchg_vol_der = self.create_derivatives(
                params,
                self.max_dchg_vol
            )
            max_dchg_vol = tf.reshape(max_dchg_vol, [-1])

            '''resistance derivatives '''
            r, r_der = self.create_derivatives(params, self.r)
            r = tf.reshape(r, [-1])

            '''eq_vol derivatives '''
            eq_vol, eq_vol_der = self.create_derivatives(params, self.eq_vol)
            eq_vol = tf.reshape(eq_vol, [-1])

            pred_max_dchg_vol = (
                max_dchg_vol + tf.reshape(max_dchg_vol_der['dCyc'], [-1])
                * tf.reshape(var_cyc, [-1])
                + tf.reshape(max_dchg_vol_der['d2Cyc'], [-1])
                * tf.reshape(var_cyc_squared, [-1])
            )

            return {
                "pred_cap": pred_cap,
                "pred_max_dchg_vol": tf.reshape(pred_max_dchg_vol, [-1]),
                "pred_eq_vol": tf.reshape(eq_vol, [-1]),
                "pred_r": tf.reshape(r, [-1]),
                "mean": mean,
                "log_sig": log_sig,
                "cap_der": cap_der,
                "max_dchg_vol_der": max_dchg_vol_der,
                "r_der": r_der,
                "eq_vol_der": eq_vol_der,
            }

        else:
            pred_max_dchg_vol = self.max_dchg_vol(params)
            pred_eq_vol = self.eq_vol(params)
            pred_r = self.r(params)

            return {
                "pred_cap": tf.reshape(
                    self.cap(params),
                    [-1, vol_tensor.shape[0]]
                ),
                "pred_max_dchg_vol": pred_max_dchg_vol,
                "pred_eq_vol": pred_eq_vol,
                "pred_r": pred_r
            }




# stores cell features
# key: index
# value: feature (matrix)
class DictionaryLayer(Layer):

    def __init__(self, num_features, num_keys):
        super(DictionaryLayer, self).__init__()
        self.num_features = num_features
        self.num_keys = num_keys
        self.kernel = self.add_weight(
            "kernel", shape=[self.num_keys, self.num_features * 2])

    def call(self, input, training=True):
        eps = tf.random.normal(
            shape=[self.num_keys, self.num_features])
        mean = self.kernel[:, :self.num_features]
        log_sig = self.kernel[:, self.num_features:]

        if not training:
            features = mean
        else:
            features = mean + tf.exp(log_sig / 2.) * eps

        # tf.gather: "fetching in the dictionary"
        fetched_features = tf.gather(features, input, axis=0)
        fetched_mean = tf.gather(mean, input, axis=0)
        fetched_log_sig = tf.gather(log_sig, input, axis=0)

        return fetched_features, fetched_mean, fetched_log_sig