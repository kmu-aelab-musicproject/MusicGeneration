import os
import pickle
import tensorflow as tf

from ..config import *


class Bar_VAE(object):
    def __init__(self, session, save_path):
        self.session = session
        self.save_path = save_path

        self._set_placeholder()
        self._build_model()

        self.minimum_loss = 9999999999

        self.saver = tf.train.Saver(max_to_keep=1)

        tf.set_random_seed(410)

    def _set_placeholder(self):
        self.bar = tf.placeholder(dtype=tf.float32, shape=[None, BAR_SIZE, PITCH_SIZE])

    def _build_model(self):
        self.network()

    def encoder(self, bar):
        with tf.variable_scope('encoder', reuse=tf.AUTO_REUSE):
            x = tf.reshape(bar, [-1, BAR_SIZE, PITCH_SIZE, 1])
            encoder1_1 = tf.layers.conv2d(x, 16, [1, 4], padding='same', strides=2, activation=tf.nn.relu)
            encoder1_1 = tf.layers.conv2d(encoder1_1, 32, [4, 1], padding='same', strides=2, activation=tf.nn.relu)

            encoder1_2 = tf.layers.conv2d(x, 16, [4, 1], padding='same', strides=2, activation=tf.nn.relu)
            encoder1_2 = tf.layers.conv2d(encoder1_2, 32, [1, 4], padding='same', strides=2, activation=tf.nn.relu)

            encoder2 = tf.concat([encoder1_1, encoder1_2], axis=-1)

            encoder3 = tf.layers.conv2d(encoder2, 16, [3, 3], padding='same', strides=2, activation=tf.nn.relu)
            encoder4 = tf.layers.conv2d(encoder3, 32, [3, 3], padding='same', strides=2, activation=tf.nn.relu)
            encoder5 = tf.layers.conv2d(encoder4, 64, [3, 3], padding='same', strides=2, activation=tf.nn.relu)
            encoder6 = tf.layers.flatten(tf.layers.conv2d(encoder5, 128, [3, 3], padding='same', strides=2,
                                                          activation=tf.nn.leaky_relu))

            self.mean = tf.layers.dense(encoder6, Z_SIZE)
            self.log_var = tf.layers.dense(encoder6, Z_SIZE)

        with tf.variable_scope('reparameterization', reuse=tf.AUTO_REUSE):
            eps = tf.random_normal(tf.shape(self.log_var), dtype=tf.float32, mean=0., stddev=1.0)

        return self.mean + tf.exp(self.log_var * 0.5) * eps

    def decoder(self, z):
        with tf.variable_scope('generator_bar_decoder', reuse=tf.AUTO_REUSE):
            _x = tf.reshape(z, [-1, 1, 1, Z_SIZE])

            with tf.variable_scope('pitch-time'):
                x1 = tf.layers.conv2d_transpose(_x, 128, [1, 6], strides=[1, 6], activation=tf.nn.relu)  # (1, 6, 128)
                x1 = tf.layers.conv2d_transpose(x1, 64, [6, 1], strides=[6, 1], activation=tf.nn.relu)  # (6, 6, 64)

            with tf.variable_scope('time-pitch'):
                x2 = tf.layers.conv2d_transpose(_x, 128, [6, 1], strides=[6, 1], activation=tf.nn.relu)  # (6, 1, 128)
                x2 = tf.layers.conv2d_transpose(x2, 64, [1, 6], strides=[1, 6], activation=tf.nn.relu)  # (6, 6, 64)

            x = tf.concat([x1, x2], axis=3)  # (6, 6, 128)

            with tf.variable_scope('merged_feature'):
                x += tf.layers.conv2d(x, 128, [1, 1], padding='same', activation=tf.nn.leaky_relu)  # (6, 6, 128)
                x = tf.layers.conv2d_transpose(x, 64, [3, 3], padding='same', strides=2,
                                               activation=tf.nn.leaky_relu)  # (12, 12, 64)
                x = tf.layers.conv2d_transpose(x, 32, [3, 3], padding='same', strides=2,
                                               activation=tf.nn.leaky_relu)  # (24, 24, 32)
                x = tf.layers.conv2d_transpose(x, 16, [3, 3], padding='same', strides=2,
                                               activation=tf.nn.relu)  # (48, 48, 16)
                x += tf.layers.conv2d(x, 16, [1, 1], padding='same', activation=tf.nn.leaky_relu)  # (48, 48, 16)
                x = tf.layers.conv2d(x, 8, [1, 1], padding='same', activation=tf.nn.relu)  # (48, 48, 8)

            return tf.layers.conv2d_transpose(x, 1, [3, 3], padding='same', strides=2)  # (96, 96, 1)

    def network(self):
        z = self.encoder(self.bar)
        self.logits = tf.reshape(self.decoder(z), [-1, BAR_SIZE, PITCH_SIZE])

        cond = tf.less(tf.nn.tanh(self.logits), tf.zeros(tf.shape(self.logits)))
        self.outputs = tf.where(cond, tf.zeros(tf.shape(self.logits)), tf.ones(tf.shape(self.logits)))

        xentropy = tf.nn.sigmoid_cross_entropy_with_logits(labels=self.bar, logits=self.logits)
        reconstruction_loss = tf.reduce_sum(xentropy)

        latent_loss = -0.5 * tf.reduce_sum(1. + self.log_var - tf.square(self.mean) - tf.exp(self.log_var), axis=1)
        self.loss = tf.reduce_mean(reconstruction_loss + latent_loss)

        self.train_op = tf.train.AdamOptimizer(0.0001).minimize(self.loss)

    def load_model(self, path):
        self.saver.restore(self.session, path)

    def train(self):
        print('train_start_bar')
        self.session.run(tf.global_variables_initializer())

        for epoch in range(1, 2500 + 1):
            loss_epoch = 0.
            for i in range(4):
                with open(os.path.join(BAR_VAE_TRAIN_DATA_PATH, 'bar_data{}.pkl'.format(i)), 'rb') as fp:
                    data = pickle.load(fp)
                for i in range(0, len(data), 256):
                    _, loss, outputs = self.session.run([self.train_op, self.loss, self.outputs], feed_dict={self.bar: data[i:i + 256]})
                    loss_epoch += loss

            with open('bar.pkl', 'wb') as fp:
                pickle.dump(outputs[0], fp)

            print('{} epoch loss: {}'.format(epoch, loss_epoch / 6))

            if loss_epoch < self.minimum_loss:
                ckpt_path = self.saver.save(self.session, os.path.join(self.save_path, 'bar_model'))
                self.minimum_loss = loss_epoch
                print(ckpt_path)
