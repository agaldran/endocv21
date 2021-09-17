#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb 25 14:36:02 2021

@author: endocv2021@generalizationChallenge
"""


import os, sys
import os.path as osp
import argparse
import numpy as np
import torch
from torchvision import transforms
from PIL import Image
from skimage import io
from skimage.transform import resize as rsz_sk
from models.get_model import get_arch
from utils.model_saving_loading import str2bool
from scipy.ndimage import binary_fill_holes as bfh
from tqdm import tqdm

def create_predFolder(task_type):
    directoryName = 'EndoCV2021'
    if not os.path.exists(directoryName):
        os.mkdir(directoryName)

    if not os.path.exists(os.path.join(directoryName, task_type)):
        os.mkdir(os.path.join(directoryName, task_type))

    return os.path.join(directoryName, task_type)

def detect_imgs(infolder, ext='.tif'):
    import os

    items = os.listdir(infolder)

    flist = []
    for names in items:
        if names.endswith(ext) or names.endswith(ext.upper()):
            flist.append(os.path.join(infolder, names))

    return np.sort(flist)

# argument parsing
parser = argparse.ArgumentParser()
parser.add_argument('--round', type=int, default=2, help='evaluation round')
parser.add_argument('--model_name', type=str, default='fpnet_dpn92_W', help='architecture')
parser.add_argument('--ckpt_path', type=str, default='final_checkpoint/', help='path to checkpoint')
parser.add_argument('--im_size', help='delimited list input, could be 512, or 480,600', type=str, default='512,640')
parser.add_argument('--tta', type=int, default=1, help='test time augmentation')

if __name__ == '__main__':
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    use_cuda = torch.cuda.is_available()
    args = parser.parse_args()
    model_name = args.model_name
    tta = args.tta
    im_size = tuple([int(item) for item in args.im_size.split(',')])
    if isinstance(im_size, tuple) and len(im_size) == 1:
        tg_size = (im_size[0], im_size[0])
    elif isinstance(im_size, tuple) and len(im_size) == 2:
        tg_size = (im_size[0], im_size[1])
    else:
        sys.exit('im_size should be a number or a tuple of two numbers')

    n_classes = 1
    ckpt_path = args.ckpt_path
    tta = args.tta
    print('* Instantiating a {} model'.format(model_name))
    model, mean, std = get_arch(model_name, n_classes=n_classes)

    checkpoint = torch.load(osp.join(ckpt_path, 'model_checkpoint.pth'), map_location='cpu')
    model.load_state_dict(checkpoint['model_state_dict'])
    model.mode = 'eval'
    model.eval()
    model = model.to(device)

    data_transforms = transforms.Compose([
        transforms.Resize(tg_size),
        transforms.ToTensor(),
        transforms.Normalize(mean, std)
    ])

    task_type = 'segmentation'
    # set image folder here!
    directoryName = create_predFolder(task_type)

    # ----> three test folders [https://github.com/sharibox/EndoCV2021-polyp_det_seg_gen/wiki/EndoCV2021-Leaderboard-guide]
    subDirs = ['EndoCV_DATA1', 'EndoCV_DATA2', 'EndoCV_DATA3']
    if args.round==1:
        im_path = '/project/def-sponsor00/endocv2021-test-noCopyAllowed-v1/'
    elif args.round==2:
        im_path = '/project/def-sponsor00/endocv2021-test-noCopyAllowed-v2/'
    for j in range(0, len(subDirs)):
        # ---> Folder for test data location!!! (Warning!!! do not copy/visulise!!!)
        imgfolder = im_path + subDirs[j]

        # set folder to save your checkpoints here!
        saveDir = osp.join(directoryName, subDirs[j] + '_pred')
        # probs_dir = osp.join(directoryName, subDirs[j] + '_probs')
        # os.makedirs(probs_dir, exist_ok=True)
        os.makedirs(saveDir, exist_ok=True)

        imgfiles = detect_imgs(imgfolder, ext='.jpg')

        file = open(saveDir + '/' + "timeElaspsed" + subDirs[j] + '.txt', mode='w')
        timeappend = []

        im_files = imgfiles[:]
        for j in tqdm(range(len(im_files))):
            """
            Grab the name of the file.
            """
            imagePath = im_files[j]
            filename = (imagePath.split('/')[-1]).split('.jpg')[0]
            # print('filename is printing::=====>>', filename)

            img = Image.open(imagePath).convert('RGB')
            size = img.size[1], img.size[0]
            img_tensor = data_transforms(img)
            del img

            # perform inference here:
            img_tensor = img_tensor.unsqueeze(0).to(device)
            with torch.no_grad():
                probs = model(img_tensor).squeeze().sigmoid().detach().cpu()

                if tta==1:
                    # outputs_lr = model(img_tensor.flip(-1)).flip(-1)
                    # probs_lr = outputs_lr.squeeze().sigmoid().detach().cpu()
                    probs_lr = model(img_tensor.flip(-1)).flip(-1).squeeze().sigmoid().detach().cpu()
                    probs = (probs + probs_lr)/2
                    del probs_lr
                elif tta ==2:
                    outputs_lr = model(img_tensor.flip(-1)).flip(-1)
                    probs_lr = outputs_lr.squeeze().sigmoid().detach().cpu()
                    outputs_ud = model(img_tensor.flip(-2)).flip(-2)
                    probs_ud = outputs_lr.squeeze().sigmoid().detach().cpu()
                    probs = (probs + probs_lr + probs_ud)/3

                del img_tensor

            preds = (probs > 0.5).numpy()

            pred = (preds * 255.0).astype(np.uint8)
            img_mask = bfh(rsz_sk(pred, (size[0], size[1]), anti_aliasing=True))


            io.imsave(osp.join(saveDir, filename + '_mask.jpg'), (img_mask * 255.0).astype('uint8'), check_contrast=False)

            del preds, probs, img_mask

    file.write('%s -----> %s \n' %
               ('average_t', np.mean(timeappend)))