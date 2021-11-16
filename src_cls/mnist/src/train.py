import torch
import torch.nn as nn
import torchvision
from torchvision import transforms
from torch.utils.tensorboard import SummaryWriter
import os
import io

import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvas
from sklearn.metrics import confusion_matrix
import pandas as pd
import seaborn as sns
import numpy as np

# Device configuration
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print('device:', device)

# Hyperparameters
image_size = 28
batch_size = 100
num_epochs = 200
learning_rate = 0.001
classes = 10


# Weights save path
weights_path = '../weights'
if not os.path.exists(weights_path):
    os.mkdir(weights_path)

# TensorBoard define
log_dir = '../../../tb_logs/cls/mnist/test1'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)
tb = SummaryWriter(log_dir=log_dir)

transform = transforms.Compose([
    # transforms.Resize(image_size),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.5],  # 1 for greyscale channels
                         std=[0.5])])

# MNIST dataset
train_dataset = torchvision.datasets.MNIST(root='../../../data/',
                                   train=True,
                                   transform=transform,
                                   download=True)

test_dataset = torchvision.datasets.MNIST(root='../../../data/',
                                   train=False,
                                   transform=transform,
                                   download=True)

# Data loader
train_data_loader = torch.utils.data.DataLoader(dataset=train_dataset,
                                          batch_size=batch_size,
                                          shuffle=True)

test_data_loader = torch.utils.data.DataLoader(dataset=test_dataset,
                                               batch_size=batch_size,
                                               shuffle=False)

# 28 -> 14 -> 7 -> 3
class CNN(torch.nn.Module):
    def __init__(self):
        super(CNN, self).__init__()
        self.keep_prob = 0.5
        # L1 ImgIn shape=(?, 28, 28, 1)
        #    Conv     -> (?, 28, 28, 32)
        #    Pool     -> (?, 14, 14, 32)
        self.layer1 = torch.nn.Sequential(
            torch.nn.Conv2d(1, 32, kernel_size=3, stride=1, padding=1),
            torch.nn.ReLU(),
            torch.nn.MaxPool2d(kernel_size=2, stride=2))

        # L2 ImgIn shape=(?, 14, 14, 32)
        #    Conv      ->(?, 14, 14, 64)
        #    Pool      ->(?, 7, 7, 64)
        self.layer2 = torch.nn.Sequential(
            torch.nn.Conv2d(32, 64, kernel_size=3, stride=1, padding=1),
            torch.nn.ReLU(),
            torch.nn.MaxPool2d(kernel_size=2, stride=2))

        # L3 ImgIn shape=(?, 7, 7, 64)
        #    Conv      ->(?, 7, 7, 128)
        #    Pool      ->(?, 4, 4, 128)
        self.layer3 = torch.nn.Sequential(
            torch.nn.Conv2d(64, 128, kernel_size=3, stride=1, padding=1),
            torch.nn.ReLU(),
            torch.nn.MaxPool2d(kernel_size=2, stride=2, padding=1))

        # L4 FC 4x4x128 inputs -> 625 outputs
        self.fc1 = torch.nn.Linear(4 * 4 * 128, 625, bias=True)
        torch.nn.init.xavier_uniform_(self.fc1.weight)
        self.layer4 = torch.nn.Sequential(
            self.fc1,
            torch.nn.ReLU(),
            torch.nn.Dropout(p = 1 - self.keep_prob))

        # L5 Final FC 625 inputs -> 10 outputs
        self.fc2 = torch.nn.Linear(625, 10, bias=True)
        torch.nn.init.xavier_uniform_(self.fc2.weight)

    def forward(self, x):
        out = self.layer1(x)
        out = self.layer2(out)
        out = self.layer3(out)
        out = out.view(out.size(0), -1)   # Flatten them for FC
        out = self.layer4(out)
        out = self.fc2(out)
        return out


model = CNN().to(device)
print(model)
criterion = torch.nn.CrossEntropyLoss().to(device)  # 비용 함수에 소프트맥스 함수 포함되어져 있음.
optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)


# Start training
total_step = len(train_data_loader)
for epoch in range(num_epochs):
    epoch_loss = 0
    epoch_acc = 0
    for i, (images, labels) in enumerate(train_data_loader):
        images = images.to(device)
        labels = labels.to(device)

        pred = model(images).to(device)
        optimizer.zero_grad()
        loss = criterion(pred, labels)
        loss.backward()
        optimizer.step()

        pred = pred.argmax(-1)
        acc = torch.sum(pred == labels)
        acc = acc / labels.size(0)

        if (i + 1) % 200 == 0:
            print('Epoch [{}/{}], Step [{}/{}], loss:{:.4f}, acc:{:.4f}'
                  .format(epoch+1, num_epochs,
                          i + 1, total_step,
                          loss.item(), acc.item()))

    with torch.no_grad():
        arr = torch.zeros((classes, classes), dtype=torch.long)

        for i, (images, labels) in enumerate(test_data_loader):
            images = images.to(device)
            labels = labels.to(device)

            pred = model(images).to(device)

            pred = pred.argmax(-1)
            acc = torch.sum(pred == labels)
            acc = acc / labels.size(0)

            arr += confusion_matrix(labels.cpu(), pred.cpu())

        class_names = [f'{i}' for i in range(10)]
        df_cm = pd.DataFrame(arr.cpu().numpy(), class_names, class_names)
        fig = plt.figure(figsize=(9, 6))
        sns.heatmap(df_cm, annot=True, fmt="d", cmap='BuGn')
        plt.xlabel("prediction")
        plt.ylabel("label (ground truth)")
        tb.add_figure(tag='confusion_matrix', global_step=epoch + 1, figure=fig)
        plt.close(fig)

