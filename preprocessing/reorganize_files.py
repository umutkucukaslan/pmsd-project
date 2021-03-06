import os
import glob
from datetime import datetime
from shutil import copyfile

"""
This script copies mri files from ADNI folder into folder that has hierarchy
    data
        patient_name
            date
                patient_name__date.nii
            date
                patient_name__date.ni
            ...
        patient_name
            ...
"""

# dataset_dir = '/Volumes/SAMSUNG/umut/thesis/ADNI'     # ADNI dataset folder
dataset_dir = "/Users/umutkucukaslan/Desktop/thesis/dataset/ADNI1_Complete_2Yr_3T"  # ADNI dataset folder
target_dir = "/Users/umutkucukaslan/Desktop/thesis/dataset/data_3t"  # target folder

patients = sorted(glob.glob(os.path.join(dataset_dir, "*")))

counter = 1
for patient in patients:
    print("Processing {} / {}".format(counter, len(patients)))
    counter += 1

    ptn = os.path.basename(patient)
    print(ptn)

    new_patient_dir = os.path.join(target_dir, ptn)

    dates = glob.glob(os.path.join(patient, "*/*"))
    for date in dates:
        print("SOURCE: ", date)

        # extract date information from folder name
        datetime_object = datetime.strptime(
            os.path.basename(date), "%Y-%m-%d_%H_%M_%S.0"
        )
        s = datetime_object.strftime("%Y-%m-%d_%H_%M_%S")

        # new image folder path
        new_image_dir = os.path.join(new_patient_dir, s)

        # create folder unless exists
        if not os.path.isdir(new_image_dir):
            os.makedirs(new_image_dir)

        image_name = ptn + "__" + s + ".nii"
        print("TARGET: ", os.path.join(new_image_dir, image_name))

        mris = glob.glob(os.path.join(date, "*/*.nii"))
        for mri in mris:
            # copy mri file, overwrite if there are multiple for the same date
            copyfile(mri, os.path.join(new_image_dir, image_name))

        print(" ")
    print("")
