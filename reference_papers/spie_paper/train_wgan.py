import datetime
import os
import statistics
import sys
import time

import tensorflow as tf
import matplotlib.pyplot as plt

from datasets.adni_dataset import get_triplets_adni_15t_dataset
from datasets.spie_dataset import get_spie_dataset
from model.losses import l2_loss_longitudinal, ssim_loss_longitudinal
from model.dcgan import make_dcgan_discriminator_model, make_dcgan_generator_model

"""
SPIE paper implementation using W-GAN (without example re-weighting)
Latent vector size: 256
Output image shape: 64 x 64 x 1

192x160 images are resized to 64x64

n_critic: 5


"""

# Input latent vector size for generator
latent_vector_size = 256

# Kernel size for generator and discriminator conv layers
kernel_size = 5


RUNTIME = "none"  # cloud, colab or none
RESTORE_FROM_CHECKPOINT = True
EXPERIMENT_NAME = "ref_spie_wgan"

PREFETCH_BUFFER_SIZE = 3
SHUFFLE_BUFFER_SIZE = 1000

BATCH_SIZE = 256
DISC_TRAIN_STEPS = 5
CLIP_DISC_WEIGHT = 0.01  # clip disc weight

EPOCHS = 2000
CHECKPOINT_SAVE_INTERVAL = 5
MAX_TO_KEEP = 5
LEARNING_RATE = 0.00005

USE_TPU = False

# set batch size easily
if len(sys.argv) > 1:
    BATCH_SIZE = int(sys.argv[1])


if USE_TPU:
    try:
        tpu = tf.distribute.cluster_resolver.TPUClusterResolver()  # TPU detection
        print("Running on TPU ", tpu.cluster_spec().as_dict()["worker"])
    except ValueError:
        raise BaseException(
            "ERROR: Not connected to a TPU runtime; please see the previous cell in this notebook for instructions!"
        )

    tf.config.experimental_connect_to_cluster(tpu)
    tf.tpu.experimental.initialize_tpu_system(tpu)
    tpu_strategy = tf.distribute.experimental.TPUStrategy(tpu)
else:
    gpus = tf.config.experimental.list_physical_devices("GPU")
    for gpu in gpus:
        tf.config.experimental.set_memory_growth(gpu, True)


if RUNTIME == "colab":
    if USE_TPU:
        EXPERIMENT_FOLDER = os.path.join("/content/experiments", EXPERIMENT_NAME)
    else:
        EXPERIMENT_FOLDER = os.path.join(
            "/content/drive/My Drive/experiments", EXPERIMENT_NAME
        )
elif RUNTIME == "cloud":
    EXPERIMENT_FOLDER = os.path.join(
        "/home/umutkucukaslan/experiments", EXPERIMENT_NAME
    )
else:
    EXPERIMENT_FOLDER = os.path.join(
        "/Users/umutkucukaslan/Desktop/thesis/experiments", EXPERIMENT_NAME
    )

if __name__ == "__main__":
    if not os.path.isdir(EXPERIMENT_FOLDER):
        os.makedirs(EXPERIMENT_FOLDER)


def log_print(msg, add_timestamp=False):
    if not isinstance(msg, str):
        msg = str(msg)
    if add_timestamp:
        msg += " (logged at {})".format(
            datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        )
    with open(os.path.join(EXPERIMENT_FOLDER, "logs.txt"), "a+") as log_file:
        log_file.write(msg + "\n")


# generator model plot path
GEN_MODEL_PLOT_PATH = os.path.join(EXPERIMENT_FOLDER, "gen_model_plot.jpg")
DIS_MODEL_PLOT_PATH = os.path.join(EXPERIMENT_FOLDER, "dis_model_plot.jpg")

# folder to save generated test images during training
if not os.path.isdir(os.path.join(EXPERIMENT_FOLDER, "figures")):
    os.makedirs(os.path.join(EXPERIMENT_FOLDER, "figures"))

# generator and discriminator
generator = make_dcgan_generator_model()
discriminator = make_dcgan_discriminator_model()

if __name__ == "__main__":
    generator.summary()
    generator.summary(print_fn=log_print)
    tf.keras.utils.plot_model(
        generator,
        to_file=GEN_MODEL_PLOT_PATH,
        show_shapes=True,
        dpi=150,
        expand_nested=True,
    )
    discriminator.summary()
    discriminator.summary(print_fn=log_print)
    tf.keras.utils.plot_model(
        discriminator,
        to_file=DIS_MODEL_PLOT_PATH,
        show_shapes=True,
        dpi=150,
        expand_nested=False,
    )

# optimizers
generator_optimizer = tf.optimizers.RMSprop(learning_rate=LEARNING_RATE)
discriminator_optimizer = tf.optimizers.RMSprop(learning_rate=LEARNING_RATE)

# checkpoint writer
checkpoint_dir = os.path.join(EXPERIMENT_FOLDER, "checkpoints")
checkpoint_prefix = os.path.join(checkpoint_dir, "ckpt")
checkpoint = tf.train.Checkpoint(
    epoch=tf.Variable(0),
    generator_optimizer=generator_optimizer,
    discriminator_optimizer=discriminator_optimizer,
    generator=generator,
    discriminator=discriminator,
)
manager = tf.train.CheckpointManager(
    checkpoint, checkpoint_dir, max_to_keep=MAX_TO_KEEP
)

if RESTORE_FROM_CHECKPOINT:
    checkpoint.restore(manager.latest_checkpoint)

if manager.latest_checkpoint:
    log_print("Restored from {}".format(manager.latest_checkpoint))
else:
    log_print("Initializing from scratch.")

initial_epoch = checkpoint.epoch.numpy() + 1


def get_generator_discriminator(return_experiment_folder=True):
    """
    This function returns the constructed and restored (if possible) sub-models that are constructed in this experiment

    :return: generator, discriminator, experiment_folder (optional)
    """
    if return_experiment_folder:
        return generator, discriminator, EXPERIMENT_FOLDER
    return generator, discriminator


if __name__ == "__main__":

    # summary file writer for tensorboard
    log_dir = os.path.join(EXPERIMENT_FOLDER, "logs")
    summary_writer = tf.summary.create_file_writer(
        os.path.join(log_dir, datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    )

    spie_dataset = get_spie_dataset(
        folder_name="training_data_15T_192x160_4slices", machine=RUNTIME
    )

    def merge_latent_vectors(latent0, latent2, a1, a2):
        # compute mid latent vector given first and last vectors and distances
        latent_mid = tf.convert_to_tensor(
            [
                (latent0[i] * a2[i] + latent2[i] * a1[i]) / (a1[i] + a2[i])
                for i in range(a1.shape[0])
            ]
        )
        return latent_mid

    def calculate_ssim(imgs, generated_imgs):
        ssims = [
            tf.image.ssim(img1, img2, max_val=1.0)
            for img1, img2 in zip(imgs, generated_imgs)
        ]
        return tf.reduce_mean([ssims[0], ssims[2]]), tf.reduce_mean(ssims[1])

    def train_step(imgs, days):
        # TODO: WGAN necessitates gradient clipping for discriminator to ensure K-Lipschitzness

        # uses three successive scan images, generates mid scan by combining latent vectors of first and
        # last scan image, computes loss for all three reconstructed images
        with tf.GradientTape() as gen_tape:
            a1 = days[1] - days[0]
            a2 = days[2] - days[1]
            latent0 = encoder(imgs[0], training=True)
            latent2 = encoder(imgs[2], training=True)
            latent_mid = merge_latent_vectors(latent0, latent2, a1, a2)
            latents = [latent0, latent_mid, latent2]
            generated_images = [decoder(x, training=True) for x in latents]
            ssim_total, ssim_missing_reconst = ssim_loss_longitudinal(
                imgs, generated_images, index=1, max_val=1.0
            )
        generator_gradients = gen_tape.gradient(
            ssim_total, generator.trainable_variables
        )
        if CLIP_BY_NORM is not None:
            generator_gradients = [
                tf.clip_by_norm(t, CLIP_BY_NORM) for t in generator_gradients
            ]
        if CLIP_BY_VALUE is not None:
            generator_gradients = [
                tf.clip_by_value(t, -CLIP_BY_VALUE, CLIP_BY_VALUE)
                for t in generator_gradients
            ]
        generator_optimizer.apply_gradients(
            zip(generator_gradients, generator.trainable_variables)
        )
        # ssim_direct_reconst, ssim_missing_reconst = calculate_ssim(
        #     imgs, generated_images
        # )
        total_reconst_loss, mid_reconst_loss = l2_loss_longitudinal(
            imgs, generated_images, index=1
        )
        return total_reconst_loss, mid_reconst_loss, ssim_total, ssim_missing_reconst

    def eval_step(imgs, days):
        a1 = days[1] - days[0]
        a2 = days[2] - days[1]
        latent0 = encoder(imgs[0], training=True)
        latent2 = encoder(imgs[2], training=True)
        latent_mid = merge_latent_vectors(latent0, latent2, a1, a2)
        latents = [latent0, latent_mid, latent2]
        generated_images = [decoder(x, training=True) for x in latents]
        total_reconst_loss, mid_reconst_loss = l2_loss_longitudinal(
            imgs, generated_images, index=1
        )
        ssim_total, ssim_missing_reconst = ssim_loss_longitudinal(
            imgs, generated_images, index=1, max_val=1.0
        )
        return total_reconst_loss, mid_reconst_loss, ssim_total, ssim_missing_reconst

    def generate_images(encoder, decoder, imgs, days, path=None, show=False):
        a1 = days[1] - days[0]
        a2 = days[2] - days[1]
        latent0 = encoder(imgs[0], training=True)
        latent2 = encoder(imgs[2], training=True)
        latent_mid = merge_latent_vectors(latent0, latent2, a1, a2)
        latents = [latent0, latent_mid, latent2]
        generated_images = [decoder(x, training=True) for x in latents]
        upper_display_list = [x.numpy()[0, :, :, 0] for x in imgs]
        lower_display_list = [x.numpy()[0, :, :, 0] for x in generated_images]
        title = ["Time 0", "Time 1", "Time 2"]
        for i in range(3):
            plt.subplot(2, 3, i + 1)
            plt.title(title[i])
            plt.imshow(upper_display_list[i], cmap=plt.get_cmap("gray"))
            plt.axis("off")
            plt.subplot(2, 3, i + 4)
            plt.imshow(lower_display_list[i], cmap=plt.get_cmap("gray"))
            plt.axis("off")
        if path is not None:
            plt.savefig(path)
        if show:
            plt.show()

    def fit(train_ds, val_ds, train_images, val_images, num_epochs, initial_epoch=0):

        assert initial_epoch < num_epochs
        train_images = iter(train_images)
        val_images = iter(val_images)
        for epoch in range(initial_epoch, num_epochs):
            print("Epoch: {}".format(epoch))
            start_time = time.time()
            val_input = next(val_images)
            image_name = str(epoch) + "_val.png"
            generate_images(
                encoder,
                decoder,
                val_input["imgs"],
                val_input["days"],
                os.path.join(EXPERIMENT_FOLDER, "figures", image_name),
                show=False,
            )
            train_input = next(train_images)
            image_name = str(epoch) + "_train.png"
            generate_images(
                encoder,
                decoder,
                train_input["imgs"],
                train_input["days"],
                path=os.path.join(EXPERIMENT_FOLDER, "figures", image_name),
                show=False,
            )

            # training
            log_print("Training epoch {}".format(epoch), add_timestamp=True)
            losses = [[], [], [], []]
            for n, inputs in train_ds.enumerate():
                imgs = inputs["imgs"]
                days = inputs["days"]
                (
                    total_reconst_loss,
                    mid_reconst_loss,
                    ssim_total,
                    ssim_missing_reconst,
                ) = train_step(imgs, days)
                losses[0].append(total_reconst_loss.numpy())
                losses[1].append(mid_reconst_loss.numpy())
                losses[2].append(ssim_total.numpy())
                losses[3].append(ssim_missing_reconst.numpy())
            losses = [statistics.mean(x) for x in losses]
            with summary_writer.as_default():
                tf.summary.scalar("total_reconst_loss", losses[0], step=epoch)
                tf.summary.scalar("mid_reconst_loss", losses[1], step=epoch)
                tf.summary.scalar("ssim_total", losses[2], step=epoch)
                tf.summary.scalar("ssim_missing_reconst", losses[3], step=epoch)
            summary_writer.flush()

            # testing
            log_print("Calculating validation losses...")
            val_losses = [[], [], [], []]
            for inputs in val_ds:
                imgs = inputs["imgs"]
                days = inputs["days"]
                (
                    total_reconst_loss,
                    mid_reconst_loss,
                    ssim_total,
                    ssim_missing_reconst,
                ) = eval_step(imgs, days)
                val_losses[0].append(total_reconst_loss.numpy())
                val_losses[1].append(mid_reconst_loss.numpy())
                val_losses[2].append(ssim_total.numpy())
                val_losses[3].append(ssim_missing_reconst.numpy())
            val_losses = [statistics.mean(x) for x in val_losses]
            with summary_writer.as_default():
                tf.summary.scalar("val_total_reconst_loss", val_losses[0], step=epoch)
                tf.summary.scalar("val_mid_reconst_loss", val_losses[1], step=epoch)
                tf.summary.scalar("val_ssim_total", val_losses[2], step=epoch)
                tf.summary.scalar("val_ssim_missing_reconst", val_losses[3], step=epoch)
            summary_writer.flush()

            end_time = time.time()
            log_print(
                "Epoch {} completed in {} seconds".format(
                    epoch, round(end_time - start_time)
                )
            )
            log_print("     total_reconst_loss       {:1.4f}".format(losses[0]))
            log_print("     mid_reconst_loss         {:1.4f}".format(losses[1]))
            log_print("     ssim_total               {:1.4f}".format(losses[2]))
            log_print("     ssim_missing_reconst     {:1.4f}".format(losses[3]))
            log_print("     val_total_reconst_loss   {:1.4f}".format(val_losses[0]))
            log_print("     val_mid_reconst_loss     {:1.4f}".format(val_losses[1]))
            log_print("     val_ssim_total           {:1.4f}".format(val_losses[2]))
            log_print("     val_ssim_missing_reconst {:1.4f}".format(val_losses[3]))

            checkpoint.epoch.assign(epoch)
            if int(checkpoint.epoch) % CHECKPOINT_SAVE_INTERVAL == 0:
                save_path = manager.save()
                log_print(
                    "Saved checkpoint for epoch {}: {}".format(
                        int(checkpoint.epoch), save_path
                    )
                )

    try:
        log_print("Fitting to the data set", add_timestamp=True)
        log_print(" ")
        log_print("Parameters:")
        log_print("Experiment name: " + str(EXPERIMENT_NAME))
        log_print("Batch size: " + str(BATCH_SIZE))
        log_print("Epochs: " + str(EPOCHS))
        log_print("Restore from checkpoint: " + str(RESTORE_FROM_CHECKPOINT))
        log_print("Chechpoint save interval: " + str(CHECKPOINT_SAVE_INTERVAL))
        log_print("Max number of checkpoints kept: " + str(MAX_TO_KEEP))
        log_print("Runtime: " + str(RUNTIME))
        log_print("Use TPU: " + str(USE_TPU))
        log_print("Prefetch buffer size: " + str(PREFETCH_BUFFER_SIZE))
        log_print("Shuffle buffer size: " + str(SHUFFLE_BUFFER_SIZE))
        log_print(
            "Input shape: ( "
            + str(INPUT_HEIGHT)
            + ", "
            + str(INPUT_WIDTH)
            + ", "
            + str(INPUT_CHANNEL)
            + " )"
        )
        log_print("Clip by norm: " + str(CLIP_BY_NORM))
        log_print("Clip by value: " + str(CLIP_BY_VALUE))
        log_print(" ")
        log_print("Initial epoch: {}".format(initial_epoch))

        train_images, val_images, _ = get_triplets_adni_15t_dataset(
            folder_name="training_data_15T_192x160_4slices", machine=RUNTIME
        )
        train_images = train_images.batch(1)
        val_images = val_images.batch(1)

        fit(
            train_ds,
            val_ds,
            train_images,
            val_images,
            EPOCHS,
            initial_epoch=initial_epoch,
        )
        # fit(
        #     train_ds.take(5),
        #     val_ds.take(2),
        #     train_images,
        #     val_images,
        #     EPOCHS,
        #     initial_epoch=initial_epoch,
        # )

        # save last checkpoint
        save_path = manager.save()
        log_print(
            "Saved checkpoint for epoch {}: {}".format(int(checkpoint.epoch), save_path)
        )
        summary_writer.close()
    except KeyboardInterrupt:
        log_print("Keyboard Interrupt", add_timestamp=True)
        # save latest checkpoint and close log file
        save_path = manager.save()
        log_print(
            "Saved checkpoint for epoch {}: {} due to KeyboardInterrupt".format(
                int(checkpoint.epoch), save_path
            )
        )
        summary_writer.close()
    except:
        summary_writer.close()
