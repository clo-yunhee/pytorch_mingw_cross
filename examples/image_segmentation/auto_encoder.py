import os 
import os.path 
import shutil 
import hashlib
import time
import random
import threading

import torch
import torch.nn as nn
import torch.nn.init as init
import torch.optim as optim
from torch.autograd import Variable

import numpy as np

from skimage import io as skio
from skimage import exposure as skie
from skimage import transform as sktr

import gi 
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

def conv3x3(in_planes, out_planes, stride=1):
    """3x3 convolution with padding"""
    return nn.Conv2d(in_planes,      out_planes, 
                     kernel_size=3,  stride=stride,
                     padding=1,      bias=False)

class BasicBlock(nn.Module):

    def __init__(self, inplanes, outplanes, stride=1):
        super(BasicBlock, self).__init__()
        self.conv1 = conv3x3(inplanes, outplanes, stride)
        self.bn1 = nn.BatchNorm2d(outplanes)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = conv3x3(outplanes, outplanes)
        self.bn2 = nn.BatchNorm2d(outplanes)
        self.stride = stride

    def forward(self, x):
        residual = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)

        out += residual
        out = self.relu(out)

        return out

class C2Block(nn.Module):

    def __init__(self, inplanes, outplanes, stride=1):
        super(C2Block, self).__init__()
        self.conv1 = conv3x3(inplanes, inplanes, stride)
        self.bn1 = nn.BatchNorm2d(inplanes)

        self.relu = nn.ReLU(inplace=True)

        self.conv2 = conv3x3(inplanes, inplanes)
        self.bn2 = nn.BatchNorm2d(inplanes)

        self.conv = nn.Conv2d(inplanes*2, outplanes, kernel_size=1, stride=1, padding=0, bias=False)
        self.norm = nn.BatchNorm2d(outplanes)

        self.stride = stride

    def forward(self, x):
        residual = x

        x1 = self.conv1(x)
        x1 = self.bn1(x1)
        x1 = self.relu(x1)

        x2 = self.conv2(x1)
        x2 = self.bn2(x2)
        x2 = self.relu(x2)

        x3 = torch.cat([x1, x2], 1)
        out = self.conv(x3)
        out = self.norm(out)

        out += residual
        out = self.relu(out)

        return out

class C4Block(nn.Module):

    def __init__(self, inplanes, outplanes, stride=1):
        super(C4Block, self).__init__()
        self.block01 = C2Block(inplanes, inplanes)
        self.block02 = C2Block(inplanes, inplanes)
        self.conv = nn.Conv2d(inplanes*2, outplanes, kernel_size=1, stride=1, padding=0, bias=False)
        self.norm = nn.BatchNorm2d(outplanes)
        self.relu = nn.ReLU(inplace=True)
        self.stride = stride

    def forward(self, x):
        residual = x

        x1 = self.block01(x)
        x2 = self.block02(x1)

        x3 = torch.cat([x1, x2], 1)
        out = self.conv(x3)
        out = self.norm(out)

        out += residual
        out = self.relu(out)

        return out

class C8Block(nn.Module):

    def __init__(self, inplanes, outplanes, stride=1):
        super(C8Block, self).__init__()
        self.block01 = C4Block(inplanes, inplanes)
        self.block02 = C4Block(inplanes, inplanes)
        self.conv = nn.Conv2d(inplanes*2, outplanes, kernel_size=1, stride=1, padding=0, bias=False)
        self.norm = nn.BatchNorm2d(outplanes)
        self.relu = nn.ReLU(inplace=True)
        self.stride = stride

    def forward(self, x):
        residual = x

        x1 = self.block01(x)
        x2 = self.block02(x1)

        x3 = torch.cat([x1, x2], 1)
        out = self.conv(x3)
        out = self.norm(out)

        out += residual
        out = self.relu(out)

        return out

class Cat3C8Block(nn.Module):

    def __init__(self, inplanes, outplanes, stride=1):
        super(Cat3C8Block, self).__init__()
        self.layer01 = C8Block(inplanes, inplanes)
        self.layer02 = C8Block(inplanes, inplanes)
        self.layer03 = C8Block(inplanes, inplanes)

        self.conv_cat = nn.Conv2d(inplanes*3, outplanes, kernel_size=1, stride=1, padding=0, bias=False)
        self.norm_cat = nn.BatchNorm2d(outplanes)
        self.relu_cat = nn.ReLU(inplace=True)

    def forward(self, x):

        x_layer01 = self.layer01(x)
        x_layer02 = self.layer02(x_layer01)
        x_layer03 = self.layer03(x_layer02)

        x_layer_cat = torch.cat([x_layer01, x_layer02, x_layer03], 1)

        x_out = self.conv_cat(x_layer_cat)
        x_out = self.norm_cat(x_out)
        x_out = self.relu_cat(x_out)

        return  x_out


class AutoEncoder(nn.Module):
    def __init__(self):
        super(AutoEncoder, self).__init__()

        self.features = nn.Sequential(
            nn.Conv2d(3, 24, kernel_size=3, stride=2, padding=1),   
            nn.BatchNorm2d(24),
            nn.ReLU(),

            nn.Conv2d(24, 48, kernel_size=3, stride=2, padding=1),           
            nn.BatchNorm2d(48),         
            nn.ReLU(),
        )

        self.encoder = nn.Sequential(Cat3C8Block(48, 96))
        
        self.decoder = nn.Sequential(
            nn.ConvTranspose2d(96, 48, kernel_size=3, stride=2, padding=1),  
            nn.BatchNorm2d(48), 
            nn.ReLU(),

            nn.ConvTranspose2d(48, 1, kernel_size=3, stride=2, padding=1),   
            nn.Tanh(),
        )

    def forward(self, x):

        x_features = self.features(x)

        x_encoded = self.encoder(x_features)

        x_decoded = self.decoder(x_encoded)

        return x_encoded, x_decoded

class Encoder_Thread(threading.Thread):
    def __init__(self, caller_slot, lock, model, 
                       str_fns, str_mask_fns, show_data, 
                       wh, max_n_loop, n_loop, idx_segment):
        super(Encoder_Thread, self).__init__()
        self.caller_slot = caller_slot
        self.lock = lock
        self.model = model
        self.str_fns = str_fns
        self.str_mask_fns = str_mask_fns
        self.show_data = show_data
        self.wh = wh
        self.max_n_loop = max_n_loop
        self.n_loop = n_loop
        self.idx_segment = idx_segment
        
    def save_bpcv_dict(self, n_loop, idx_segment):
        bpcv_dict = {}   
        bpcv_dict["n_loop"] = n_loop
        bpcv_dict["idx_loop"] = idx_segment
        str_pth_fn = "./models/bpcv_encoder_{0:0>5d}.pth".format(idx_segment+1)
        bpcv_dict["net_state"] = self.model.state_dict()
        print("model save to : {}".format(str_pth_fn))
        torch.save(bpcv_dict, str_pth_fn)
     
    def run(self):
        batch_sizes = [10, 10, 20, 20, 20, 20]  
        lrs = [0.01*0.5, 0.01*0.2, 0.01*0.2, 0.01*0.1, 0.01*0.1, 0.01*0.1*0.5]
        m_loops = [0, 6000*1, 6000*2, 6000*3, 6000*4, 6000*5]  

        len_fns = len(self.str_fns)
        mess_quit = False

        for n in range(self.n_loop, self.max_n_loop+1):

            self.model.train()
            optimizer = torch.optim.Adam(self.model.parameters(), lrs[n])
            loss_func = nn.MSELoss()

            batch_size = batch_sizes[n]

            if (self.idx_segment != 0):   
                self.idx_segment += 1

            print("batch_size: {0:0>5d}  lr: {1:.4f}".format(batch_sizes[n], lrs[n]) )
            print("..............................................................................")      

            imgs_ten = torch.Tensor(batch_size,3,self.wh,self.wh)
            imgs_mask_ten = torch.Tensor(batch_size,1,self.wh,self.wh)

            for idx_loop in range(self.idx_segment, m_loops[n]+6000):
            #{
                idxs = np.random.randint(0, len_fns, batch_size)

                for i in range(0, batch_size):
                    idx = idxs[i]
                    img_src = skio.imread(self.str_fns[idx])
                    img_resize = sktr.resize(img_src, (self.wh, self.wh), mode = 'reflect', anti_aliasing = True )
                    img_rescale = skie.rescale_intensity(img_resize, in_range="image", out_range=(0.0, 1.0) )        
                    img_data = img_rescale - 0.5
                    img_data = img_data / 0.5
                    img_data = img_data.transpose((2, 0, 1))  

                    img_mask_gray = skio.imread(self.str_mask_fns[idx], as_gray=True)
                    img_mask_regray = sktr.resize(img_mask_gray, (self.wh, self.wh), mode = 'reflect', anti_aliasing = True )
                    img_mask_rescale = skie.rescale_intensity(img_mask_regray, in_range="image", out_range=(0.0, 1.0) )        
                    img_mask_data = img_mask_rescale - 0.5  
                    img_mask_data = img_mask_data / 0.5
                    #img_mask_data = img_mask_rescale

                    imgs_ten[i] = torch.from_numpy(img_data) 
                    imgs_mask_ten[i][0] = torch.from_numpy(img_mask_data) 
                    #imgs_mask_ten[i][1] = torch.from_numpy(1.0 - img_mask_data)

                x_encoded, x_decoded = self.model(imgs_ten)   
                loss = loss_func(x_decoded, imgs_mask_ten)     
                optimizer.zero_grad()               # clear gradients for this training step
                loss.backward()                     # backpropagation, compute gradients
                optimizer.step()                    # apply gradients   

                np_imgs = imgs_ten.detach().numpy()
                np_mask_imgs = imgs_mask_ten.detach().numpy()
                np_decoded = x_decoded.detach().numpy()

                self.lock.acquire()
                mess_quit = self.show_data["mess_quit"]
                self.lock.release()

                if (mess_quit == True):
                    self.save_bpcv_dict(n, idx_loop)
                    return  

                if (idx_loop % 10 == 0): 
                    print("loop_{0:0>5d} idx: {1:0>6d} {2:0>6d} ...  loss: {3:.7f}"
                           .format(idx_loop, idxs[0], idxs[1], loss.data.numpy()))

                if (idx_loop % 10 == 0):
                    self.lock.acquire()
                    self.show_data["np_imgs"] = np_imgs.copy()
                    self.show_data["np_mask_imgs"] = np_mask_imgs.copy()
                    self.show_data["np_decoded"] = np_decoded.copy()
                    self.lock.release()
                    GLib.idle_add(self.caller_slot, "torch data")
                    #time.sleep(1.0)   

                if ((idx_loop+1) % 1000 == 0):
                    self.save_bpcv_dict(n, idx_loop)
            #}
            
            self.idx_segment = m_loops[n]+6000-1






