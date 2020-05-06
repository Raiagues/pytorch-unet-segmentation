import os
import json
import random
from dataclasses import dataclass

import skimage.io
import skimage.transform

import numpy as np

import torch
from torch.utils.data import Dataset
from torchvision import transforms
import torchvision.transforms.functional as TF


@dataclass
class DataAugmentation(object):

    central_crop_size: int = 512
    h_flipping_chance: float = 0.50
    brightness_rate: float = 0.10
    contrast_rate: float = 0.10
    saturation_rate: float = 0.10
    hue_rate: float = 0.05

    def augment(self, image, mask):
        # Color and illumination changes
        image = transforms.ColorJitter(brightness=self.brightness_rate,
                                       contrast=self.contrast_rate,
                                       saturation=self.saturation_rate,
                                       hue=self.hue_rate)(image)

        # Random crop the image
        random_crop = PairRandomCrop(image_size=self.central_crop_size)
        image, mask = random_crop(image, mask)

        # Random horizontal flipping
        if random.random() > self.h_flipping_chance:
            image, mask = TF.hflip(image), TF.hflip(mask)

        return image, mask


class DeepFashion2Dataset(Dataset):

    def __init__(self,
                 path: str,
                 image_resize: int,
                 subset: str = 'train',
                 data_augmentation: DataAugmentation = None):
        self._image_resize = image_resize

        valid_subsets = ['train', 'validation', 'test']
        if subset not in valid_subsets:
            raise ValueError(
                f'Subset must be one of {valid_subsets}. Is "{subset}"'
            )

        self._data_augmentation = data_augmentation

        with open(os.path.join(path, 'data.json'), 'r') as file:
            data = json.load(file)

        images = [os.path.join(path, row['image_path'])
                  for row in data if row['set'] == subset]
        masks = [os.path.join(path, row['mask_path'])
                 for row in data if row['set'] == subset]

        # Read only existing image + mask pairs
        self._image_mask_pairs = np.array([
            (img, mask)
            for (img, mask) in zip(images, masks)
            if os.path.isfile(img) and os.path.isfile(mask)
        ])
        print(f'Read {len(images)} images, built ' +
              f'{len(self._image_mask_pairs)} image pairs')

    def _transform(self, image, mask):
        image = TF.to_pil_image(_resize_image(image, self._image_resize))
        mask = TF.to_pil_image(_resize_mask(mask, self._image_resize))

        if self._data_augmentation is not None:
            image, mask = self._data_augmentation.augment(image, mask)

        # Image normalization
        image = transforms.ToTensor()(image)
        image = transforms.Normalize(mean=(0,), std=(1,))(image)
        return image, np.array(mask)

    def __len__(self):
        return len(self._image_mask_pairs)

    def __getitem__(self, idx):

        if torch.is_tensor(idx):
            idx = idx.tolist()

        image_path, mask_path = self._image_mask_pairs[idx]
        image = skimage.io.imread(image_path)
        mask = skimage.io.imread(mask_path)
        return self._transform(image, mask)


def _resize_image(img: np.ndarray, new_size: int) -> np.ndarray:
    return skimage.transform.resize(img,
                                    (new_size, new_size),
                                    preserve_range=True,
                                    order=0).astype('uint8')


def _resize_mask(mask: np.ndarray, new_size: int) -> np.ndarray:
    return skimage.transform.resize(mask,
                                    (new_size, new_size),
                                    order=0,  # mode=nearest
                                    anti_aliasing=False,
                                    preserve_range=True).astype('uint8')


class PairRandomCrop(object):

    def __init__(self, image_size: int):
        self._image_size = image_size

    def __call__(self, image, mask):
        # Compute paddings for random crop given dimensions
        crop_params = transforms.RandomCrop.get_params(
            image,
            output_size=(self._image_size, self._image_size)
        )
        start_y, start_x, new_height, new_width = crop_params
        # Apply crop given computed paddings
        image = TF.crop(image, start_y, start_x, new_height, new_width)
        mask = TF.crop(mask, start_y, start_x, new_height, new_width)
        return image, mask


import matplotlib.pyplot as plt

if __name__ == '__main__':

    augmentation = DataAugmentation(
        central_crop_size=512,
        h_flipping_chance=0.50,
        brightness_rate=0.10,
        contrast_rate=0.10,
        saturation_rate=0.10,
        hue_rate=0.05
    )

    data = DeepFashion2Dataset('full_dataset',
                               image_resize=580,
                               data_augmentation=augmentation)

    n_rows = 5
    idxs = [random.randint(0, len(data)) for _ in range(n_rows)]
    fig, axs = plt.subplots(n_rows, 2, figsize=(7.0, n_rows*3.0))

    for i, idx in enumerate(idxs):
        image, mask = data[idx]
        axs[i][0].imshow(np.transpose(image, (1, 2, 0)))
        axs[i][0].set_title('Sample image #{}'.format(i))
        axs[i][1].imshow(mask)
        labels = np.unique(mask)
        axs[i][1].set_title('Sample mask #{}. Labels: {}'.format(i, labels))

    plt.tight_layout()
    plt.show()
