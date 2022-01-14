import os

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
import torchvision
from torchvision import transforms, datasets
import matplotlib.pyplot as plt
from sklearn.metrics import confusion_matrix
import pandas as pd
import seaborn as sns

from utiles.tensorboard import getTensorboard
from utiles.data import getSubDataset
from utiles.imbalance_cifar10_loader import ImbalanceCIFAR10DataLoader
from models.expert_resnet_cifar import resnet32
from loss import DiverseExpertLoss

# Define hyper-parameters
name = 'experiments3/Resnet_s/classifier'
tensorboard_path = f'../../tb_logs/{name}'

num_workers = 4
num_epochs = 200
batch_size = 128
imb_factor = 0.01

learning_rate = 0.1
weight_decay = 5e-4
momentum = 0.9
nesterov = True

return_feature = True



# Device configuration
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print('device:', device)

# Define Tensorboard
tb = getTensorboard(tensorboard_path)

# Define DataLoader
train_data_loader = ImbalanceCIFAR10DataLoader(data_dir='../../data',
                                              batch_size=batch_size,
                                              shuffle=True,
                                              num_workers=num_workers,
                                              training=True,
                                              imb_factor=imb_factor)

test_data_loader = ImbalanceCIFAR10DataLoader(data_dir='../../data',
                                              batch_size=batch_size,
                                              shuffle=False,
                                              num_workers=num_workers,
                                              training=False)


print("Number of train dataset", len(train_data_loader.dataset))
print("Number of test dataset", len(test_data_loader.dataset))

print(train_data_loader.cls_num_list)
cls_num_list = train_data_loader.cls_num_list


# Define model
model = resnet32(num_classes=10, use_norm=True).to(device)
print(model)

criterion = DiverseExpertLoss(cls_num_list=cls_num_list, tau=4)

# SAVE_PATH = f'../../weights/experiments2/Resnet_s/GAN/D_200.pth'
# model.load_state_dict(torch.load(SAVE_PATH), strict=False)


# Define optimizer
# optimizer = torch.optim.Adam(model.parameters(),
#                             lr=learning_rate,
#                             # momentum=momentum,
#                             weight_decay=weight_decay)

optimizer = torch.optim.SGD(model.parameters(),
                            momentum=momentum,
                            lr=learning_rate,
                            weight_decay=weight_decay,
                            nesterov=nesterov)

train_best_accuracy = 0
train_best_accuracy_epoch = 0
test_best_accuracy = 0
test_best_accuracy_epoch = 0


step1 = 160
step2 = 180
gamma = 0.1
warmup_epoch = 5

def lr_lambda(epoch):
    if epoch >= step2:
        lr = gamma * gamma
    elif epoch >= step1:
        lr = gamma
    else:
        lr = 1

    """Warmup"""
    if epoch < warmup_epoch:
        lr = lr * float(1 + epoch) / warmup_epoch
    print(lr)
    return lr

lr_scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)

# Training model
for epoch in range(num_epochs):
    train_loss = 0.0
    train_accuracy = 0.0
    test_loss = 0.0
    test_accuracy = 0.0

    for train_idx, data in enumerate(train_data_loader):
        img, target = data
        img, target = img.to(device), target.to(device)
        batch = img.size(0)

        optimizer.zero_grad()

        model.train()
        extra_info = {}
        output = model(img)

        logits = output["logits"]
        extra_info.update({
            "logits": logits.transpose(0, 1)
        })

        output = output["output"]
        loss = criterion(output_logits=output, target=target, extra_info=extra_info)
        # loss = F.cross_entropy(pred, target)
        loss.backward()
        optimizer.step()


        train_loss += loss.item()
        pred = output.argmax(dim=1)
        train_accuracy += torch.sum(pred == target).item()
        # print(f"epochs: {epoch}, iter: {train_idx}/{len(train_data_loader)}, loss: {loss.item()}")

    model.eval()
    with torch.no_grad():
        for test_idx, data in enumerate(test_data_loader):
            img, target = data
            img, target = img.to(device), target.to(device)
            batch = img.size(0)

            output = model(img)
            logits = output["logits"]
            extra_info.update({
                "logits": logits.transpose(0, 1)
            })
            output = output["output"]

            loss = criterion(output_logits=output, target=target, extra_info=extra_info)
            # loss = F.cross_entropy(pred, target)
            test_loss += loss.item()

            pred = output.argmax(-1)
            test_accuracy += torch.sum(pred == target).item()

    # print('train_loss', train_loss)
    # print('train_len', len(train_data_loader))
    # print('test_loss', test_loss)
    # print('len', len(test_data_loader))

    train_loss = train_loss/len(train_data_loader)
    test_loss = test_loss/len(test_data_loader)
    train_accuracy = train_accuracy/len(train_data_loader.dataset)
    test_accuracy = test_accuracy/len(test_data_loader.dataset)

    print(len(train_data_loader))
    print(len(train_data_loader.dataset))

    if train_best_accuracy < train_accuracy:
        train_best_accuracy = train_accuracy
        train_best_accuracy_epoch = epoch
    if test_best_accuracy < test_accuracy:
        test_best_accuracy = test_accuracy
        test_best_accuracy_epoch = epoch


    print(f"epochs: {epoch}, \n"
          f"train_loss: {train_loss:.4}, \n"
          f"train_acc: {train_accuracy:.4}, \n"
          f"test_loss: {test_loss:.4}, \n"
          f"test_acc: {test_accuracy:.4}, \n"
          f"train_best_acc: {train_best_accuracy:.4} ({train_best_accuracy_epoch}), \n"
          f"test_best_acc: {test_best_accuracy:.4} ({test_best_accuracy_epoch})")

    print(max([param_group['lr'] for param_group in optimizer.param_groups]),
                min([param_group['lr'] for param_group in optimizer.param_groups]))
    lr_scheduler.step()







