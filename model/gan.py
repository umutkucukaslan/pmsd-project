import tensorflow as tf


def upsample(filters, size, apply_dropout=False):
    initializer = tf.random_normal_initializer(0., 0.02)

    result = tf.keras.Sequential()
    result.add(
        tf.keras.layers.Conv2DTranspose(filters, size, strides=2,
                                        padding='same',
                                        kernel_initializer=initializer,
                                        use_bias=False))

    result.add(tf.keras.layers.BatchNormalization())

    if apply_dropout:
        result.add(tf.keras.layers.Dropout(0.5))

    result.add(tf.keras.layers.ReLU())

    return result


def downsample(filters, size, apply_batchnorm=True):
    initializer = tf.random_normal_initializer(0., 0.02)

    result = tf.keras.Sequential()
    result.add(
        tf.keras.layers.Conv2D(filters, size, strides=2, padding='same',
                               kernel_initializer=initializer, use_bias=False))

    if apply_batchnorm:
        result.add(tf.keras.layers.BatchNormalization())

    result.add(tf.keras.layers.LeakyReLU())

    return result


def generator():
    inputs = tf.keras.layers.Input(shape=[256, 256, 3])

    down_stack = [
        downsample(64, 4, apply_batchnorm=False),  # (bs, 128, 128, 64)
        downsample(128, 4),  # (bs, 64, 64, 128)
        downsample(256, 4),  # (bs, 32, 32, 256)
        downsample(512, 4),  # (bs, 16, 16, 512)
        downsample(512, 4),  # (bs, 8, 8, 512)
        downsample(512, 4),  # (bs, 4, 4, 512)
        downsample(512, 4),  # (bs, 2, 2, 512)
        downsample(512, 4),  # (bs, 1, 1, 512)
    ]

    up_stack = [
        upsample(512, 4, apply_dropout=True),  # (bs, 2, 2, 1024)
        upsample(512, 4, apply_dropout=True),  # (bs, 4, 4, 1024)
        upsample(512, 4, apply_dropout=True),  # (bs, 8, 8, 1024)
        upsample(512, 4),  # (bs, 16, 16, 1024)
        upsample(256, 4),  # (bs, 32, 32, 512)
        upsample(128, 4),  # (bs, 64, 64, 256)
        upsample(64, 4),  # (bs, 128, 128, 128)
    ]

    OUTPUT_CHANNELS = 3
    initializer = tf.random_normal_initializer(0., 0.02)
    last = tf.keras.layers.Conv2DTranspose(OUTPUT_CHANNELS, 4,
                                           strides=2,
                                           padding='same',
                                           kernel_initializer=initializer,
                                           activation='tanh')  # (bs, 256, 256, 3)

    x = inputs

    # Downsampling through the model
    skips = []
    for down in down_stack:
        x = down(x)
        skips.append(x)

    skips = reversed(skips[:-1])

    # Upsampling and establishing the skip connections
    for up, skip in zip(up_stack, skips):
        x = up(x)
        x = tf.keras.layers.Concatenate()([x, skip])

    x = last(x)

    return tf.keras.Model(inputs=inputs, outputs=x)


def get_mnist_discriminator():
    input_shape = [28, 28, 1]
    initializer = tf.random_normal_initializer(0., 0.02)

    inp = tf.keras.layers.Input(shape=input_shape, name='input_image')
    tar = tf.keras.layers.Input(shape=input_shape, name='target_image')

    x = tf.keras.layers.concatenate([inp, tar])  # (bs, 28, 28, channels*2=2)

    down1 = downsample(8, 3, False)(x)  # (bs, 14, 14, 8)
    down1_padded = tf.keras.layers.ZeroPadding2D(padding=(1,1))(down1)  # (b, 16, 16, 8)
    down2 = downsample(16, 3)(down1)  # (bs, 8, 8, 16)
    down3 = downsample(32, 3)(down2)  # (bs, 4, 4, 32)
    down4 = downsample(32, 3)(down3)  # (bs, 2, 2, 64)

    last = tf.keras.layers.Conv2D(1, 1, strides=1, kernel_initializer=initializer)(down4)   # (bs, 2, 2, 1)

    return tf.keras.Model(inputs=[inp, tar], outputs=last)


def get_discriminator_2020_04_06():
    input_shape = [256, 256, 1]
    kernel_size = 3
    batch_norm = True
    initializer = tf.random_normal_initializer(0., 0.02)

    inp = tf.keras.layers.Input(shape=input_shape, name='input_image')
    tar = tf.keras.layers.Input(shape=input_shape, name='target_image')

    x = tf.keras.layers.concatenate([inp, tar])  # (bs, 256, 256, channels*2=2)

    x = downsample(64, kernel_size, batch_norm)(x)  # (bs, 128, 128, 64)
    x = downsample(128, kernel_size, batch_norm)(x)  # (bs, 64, 64, 128)
    x = downsample(256, kernel_size, batch_norm)(x)  # (bs, 32, 32, 256)
    x = downsample(256, kernel_size, batch_norm)(x)  # (bs, 16, 16, 256)

    x = tf.keras.layers.Conv2D(256, kernel_size, strides=1, padding='same', kernel_initializer=initializer,
                               use_bias=False)(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.LeakyReLU()(x)      # (bs, 16, 16, 512)

    x = tf.keras.layers.Conv2D(128, kernel_size, strides=1, padding='same', kernel_initializer=initializer,
                               use_bias=False)(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.LeakyReLU()(x)  # (bs, 16, 16, 128)

    last = tf.keras.layers.Conv2D(1, 1, strides=1, kernel_initializer=initializer)(x)  # (bs, 16, 16, 1)

    return tf.keras.Model(inputs=[inp, tar], outputs=last, name='discriminator')


def get_discriminator(input_shape=(256, 256, 1), kernel_size=3, batch_norm=True, initializer=tf.random_normal_initializer(0., 0.02)):

    inp = tf.keras.layers.Input(shape=input_shape, name='input_image')
    tar = tf.keras.layers.Input(shape=input_shape, name='target_image')

    x = tf.keras.layers.concatenate([inp, tar])  # (bs, H, W, channels*2=2)

    x = downsample(64, kernel_size, batch_norm)(x)  # (bs, H/2, W/2, 64)
    x = downsample(128, kernel_size, batch_norm)(x)  # (bs, H/4, W/4, 128)
    x = downsample(256, kernel_size, batch_norm)(x)  # (bs, H/8, W/8, 256)
    x = downsample(256, kernel_size, batch_norm)(x)  # (bs, H/16, W/16, 256)

    x = tf.keras.layers.Conv2D(256, kernel_size, strides=1, padding='same', kernel_initializer=initializer,
                               use_bias=False)(x)
    if batch_norm:
        x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.LeakyReLU()(x)      # (bs, H/16, W/16, 512)

    x = tf.keras.layers.Conv2D(128, kernel_size, strides=1, padding='same', kernel_initializer=initializer,
                               use_bias=False)(x)
    if batch_norm:
        x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.LeakyReLU()(x)  # (bs, H/16, W/16, 128)

    last = tf.keras.layers.Conv2D(1, 1, strides=1, kernel_initializer=initializer)(x)  # (bs, H/16, W/16, 1)

    return tf.keras.Model(inputs=[inp, tar], outputs=last, name='discriminator')


def get_discriminator_2020_05_01_inputsize64x64():
    input_shape = [64, 64, 1]
    kernel_size = 3
    batch_norm = True
    initializer = tf.random_normal_initializer(0., 0.02)

    inp = tf.keras.layers.Input(shape=input_shape, name='input_image')
    tar = tf.keras.layers.Input(shape=input_shape, name='target_image')

    x = tf.keras.layers.concatenate([inp, tar])  # (bs, 64, 64, channels*2=2)

    x = downsample(64, kernel_size, batch_norm)(x)  # (bs, 32, 32, 64)
    x = downsample(128, kernel_size, batch_norm)(x)  # (bs, 16, 16, 128)
    x = downsample(256, kernel_size, batch_norm)(x)  # (bs, 8, 8, 256)
    x = downsample(256, kernel_size, batch_norm)(x)  # (bs, 4, 4, 256)

    x = tf.keras.layers.Conv2D(256, kernel_size, strides=1, padding='same', kernel_initializer=initializer,
                               use_bias=False)(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.LeakyReLU()(x)      # (bs, 4, 4, 512)

    x = tf.keras.layers.Conv2D(128, kernel_size, strides=1, padding='same', kernel_initializer=initializer,
                               use_bias=False)(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.LeakyReLU()(x)  # (bs, 4, 4, 128)

    last = tf.keras.layers.Conv2D(1, 1, strides=1, kernel_initializer=initializer)(x)  # (bs, 4, 4, 1)

    return tf.keras.Model(inputs=[inp, tar], outputs=last, name='discriminator')





def get_discriminator_2020_04_13():
    input_shape = [256, 256, 1]
    kernel_size = 3
    batch_norm = True
    initializer = tf.random_normal_initializer(0., 0.02)

    inp = tf.keras.layers.Input(shape=input_shape, name='input_image')
    tar = tf.keras.layers.Input(shape=input_shape, name='target_image')

    x = tf.keras.layers.concatenate([inp, tar])  # (bs, 256, 256, channels*2=2)

    x = downsample(64, kernel_size, batch_norm)(x)  # (bs, 128, 128, 64)
    x = downsample(128, kernel_size, batch_norm)(x)  # (bs, 64, 64, 128)
    x = downsample(256, kernel_size, batch_norm)(x)  # (bs, 32, 32, 256)
    x = downsample(256, kernel_size, batch_norm)(x)  # (bs, 16, 16, 256)

    x = tf.keras.layers.Conv2D(256, kernel_size, strides=1, padding='same', kernel_initializer=initializer,
                               use_bias=False)(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.LeakyReLU()(x)      # (bs, 16, 16, 512)

    x = tf.keras.layers.Conv2D(128, kernel_size, strides=1, padding='same', kernel_initializer=initializer,
                               use_bias=False)(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.LeakyReLU()(x)  # (bs, 16, 16, 128)

    last = tf.keras.layers.Conv2D(1, 1, strides=1, kernel_initializer=initializer)(x)  # (bs, 16, 16, 1)

    return tf.keras.Model(inputs=[inp, tar], outputs=last, name='discriminator')