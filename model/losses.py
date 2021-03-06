import tensorflow as tf


def ssim_loss(target_img, predicted_img, max_val=1):
    return -tf.reduce_mean(tf.image.ssim(target_img, predicted_img, max_val=max_val))


def ssim_loss_longitudinal(target_img, predicted_img, max_val=1, index=1):
    # computes average loss of ssim loss for three images
    losses = [ssim_loss(x, y, max_val) for x, y in zip(target_img, predicted_img)]
    total_loss = 0
    for loss in losses:
        total_loss += loss
    return total_loss, losses[index]


def l2_loss(target_y, predicted_y):
    return tf.reduce_mean(tf.square(target_y - predicted_y))


def l2_loss_longitudinal(imgs, generated_imgs, index=1):
    # calculated L2 losses between sequence of input and target images, returns sum of losses and indexed loss
    losses = [l2_loss(x, y) for x, y in zip(generated_imgs, imgs)]
    total_loss = 0
    for loss in losses:
        total_loss += loss
    return total_loss, losses[index]


def wgan_gp_loss_longitudinal(discriminator, imgs, generated_imgs, lambda_gp):
    gen_loss, disc_loss, gp_loss = 0, 0, 0
    for x_real, x_fake in zip(imgs, generated_imgs):
        gen_loss_inc, disc_loss_inc, gp_loss_inc = wgan_gp_loss(
            discriminator, x_real, x_fake, lambda_gp
        )
        gen_loss += gen_loss_inc
        disc_loss += disc_loss_inc
        gp_loss += gp_loss_inc
    return gen_loss, disc_loss, gp_loss


def wgan_gp_loss(f, x_real, x_fake, lambda_gp):
    """
    WGAN-GP loss implementation. Returns disc_loss, gen_loss

    :param f: discriminator network
    :param x_real: real example / real image
    :param x_fake: fake example / generated image
    :param lambda_gp: weight of gradient penalty
    :return: disc_loss, gen_loss
    """
    disc_real_output = tf.reduce_mean(f([x_real, x_real], training=True))
    disc_fake_output = tf.reduce_mean(f([x_fake, x_real], training=True))

    x_real_shape = tf.shape(x_real).numpy()
    shape = [1 for i in range(len(x_real_shape))]
    shape[0] = x_real_shape[0]

    alpha = tf.random.uniform(shape=shape, minval=0.0, maxval=1.0)
    x_hat = x_real + alpha * (x_real - x_fake)
    with tf.GradientTape() as tape:
        tape.watch(x_hat)
        x_hat_out = f([x_hat, x_real], training=True)
    grad = tape.gradient(x_hat_out, x_hat)
    grad_norm = tf.norm(tf.reshape(grad, [tf.shape(grad)[0], -1]), axis=1)
    gp = tf.reduce_mean((grad_norm - 1.0) ** 2)
    disc_loss = (
        disc_fake_output - disc_real_output + lambda_gp * gp
    )  # discriminator loss

    gen_loss = -disc_fake_output  # generator loss

    return gen_loss, disc_loss, gp


def wgan_gp_loss_progressive_gan(f, x_real, x_fake, lambda_gp, weight=None):
    """
    WGAN-GP loss implementation. Returns disc_loss, gen_loss

    :param f: discriminator network
    :param x_real: real example / real image
    :param x_fake: fake example / generated image
    :param lambda_gp: weight of gradient penalty
    :return: disc_loss, gen_loss
    """
    if weight is not None:
        disc_real_output = tf.reduce_mean(f([x_real, weight], training=True))
        disc_fake_output = tf.reduce_mean(f([x_fake, weight], training=True))
    else:
        disc_real_output = tf.reduce_mean(f(x_real, training=True))
        disc_fake_output = tf.reduce_mean(f(x_fake, training=True))

    x_real_shape = tf.shape(x_real).numpy()
    shape = [1 for i in range(len(x_real_shape))]
    shape[0] = x_real_shape[0]

    alpha = tf.random.uniform(shape=shape, minval=0.0, maxval=1.0)
    x_hat = x_real + alpha * (x_real - x_fake)
    with tf.GradientTape() as tape:
        tape.watch(x_hat)
        if weight is not None:
            x_hat_out = f([x_hat, weight], training=True)
        else:
            x_hat_out = f(x_hat, training=True)
    grad = tape.gradient(x_hat_out, x_hat)
    grad_norm = tf.norm(tf.reshape(grad, [tf.shape(grad)[0], -1]), axis=1)
    gp = tf.reduce_mean((grad_norm - 1.0) ** 2)
    disc_loss = (
        disc_fake_output - disc_real_output + lambda_gp * gp
    )  # discriminator loss

    gen_loss = -disc_fake_output  # generator loss

    return gen_loss, disc_loss, gp


def vae_loss(x_real, x_fake, latent_mean, latent_std, normal_std=1):
    """
    This loss assumes that latent variables are generated using Gaussian distribution of zero mean and unit variance.

    Architecture:
    x: input image
    latent_mean, latent_std = encoder(x)
    epsilon = N(0, 1)   random vector from normal distribution
    latent = latent_mean + epsilon * latent_std
    x_out = decoder(latent)

    :param x_real: input image
    :param x_fake: generated image 
    :param latent_mean:
    :param latent_std:
    :return:
    """
    epsilon = 1e-3
    kl_loss = tf.reduce_mean(
        tf.math.log(normal_std / (tf.math.abs(latent_std) + epsilon))
        + (
            latent_std * latent_std
            + latent_mean * latent_mean
            - normal_std * normal_std
        )
        / (2 * normal_std * normal_std)
    )
    reconst_loss = tf.reduce_mean(tf.square(x_real - x_fake))
    total_loss = reconst_loss + kl_loss

    return total_loss, reconst_loss, kl_loss


def binary_cross_entropy_with_logits(y_true, y_pred, from_logits=False):
    """
    Binary cross entropy loss for each sample in the batch

    :param y_true: [B, ...]
    :param y_pred: [B, ...]
    :return: [B]
    """
    y_true = tf.reshape(y_true, [y_true.shape[0], -1])
    y_pred = tf.reshape(y_pred, [y_true.shape[0], -1])
    ce = tf.keras.backend.binary_crossentropy(y_true, y_pred, from_logits=from_logits)
    ce = tf.reduce_mean(ce, axis=-1)
    return ce
