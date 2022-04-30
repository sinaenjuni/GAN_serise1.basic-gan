
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim.lr_scheduler import LambdaLR
from torchmetrics.functional import confusion_matrix
from torch.optim import SGD, Adam
from models.resnet import resnet18, resnet34
from models.generator import Generator, linear, snlinear, deconv2d, sndeconv2d

import pytorch_lightning as pl
from torchsummaryX import summary
import matplotlib.pyplot as plt
from torchvision.utils import make_grid


def accNaccPerCls(pred, label, num_class):
    cm = torch.nan_to_num(confusion_matrix(pred, label, num_classes=num_class))
    acc = torch.nan_to_num(cm.trace() / cm.sum())
    acc_per_cls = torch.nan_to_num(cm.diagonal() / cm.sum(0))

    return cm, acc, acc_per_cls


def d_loss_function(real_logit, fake_logit):
    # real_loss = F.binary_cross_entropy_with_logits(real_logit, torch.ones_like(real_logit))
    # fake_loss = F.binary_cross_entropy_with_logits(fake_logit, torch.zeros_like(fake_logit))
    real_loss = F.relu(1. - real_logit).mean()
    fake_loss = F.relu(1. + fake_logit).mean()

    d_loss = real_loss + fake_loss
    return d_loss

def g_loss_function(fake_logit):
    # g_loss = F.binary_cross_entropy_with_logits(fake_logit, torch.ones_like(fake_logit))
    g_loss = -fake_logit.mean()

    return g_loss


class FcNAdvModuel(nn.Module):
    def __init__(self, linear, num_classes):
        super(FcNAdvModuel, self).__init__()
        # self.cls = linear(in_features=512, out_features=num_classes)
        self.adv = linear(in_features=512, out_features=1)

    def forward(self, x):
        # return self.adv(x), self.cls(x)
        return self.adv(x)

class ACGAN(pl.LightningModule):
    def __init__(self,
                 model,
                 num_classes,
                 bn,
                 sn,
                 learning_rate,
                 image_size,
                 image_channel,
                 std_channel,
                 latent_dim,
                 **kwargs):
        super(ACGAN, self).__init__()
        self.save_hyperparameters()
        self.fixed_noise = torch.randn(10, latent_dim).cuda().repeat(10, 1)

        if sn:
            self.G = Generator(linear=snlinear,
                      deconv=sndeconv2d,
                      image_size=image_size,
                      image_channel=image_channel,
                      std_channel=std_channel,
                      latent_dim=latent_dim,
                      bn=bn)
        else:
            self.G = Generator(linear=linear,
                      deconv=deconv2d,
                      image_size=image_size,
                      image_channel=image_channel,
                      std_channel=std_channel,
                      latent_dim=latent_dim,
                      bn=bn)

        if model == 'resnet18':
            self.D = resnet18(num_classes=num_classes, sn=sn)
        elif model == 'resnet34':
            self.D = resnet34(num_classes=num_classes, sn=sn)

        if sn:
            self.D.fc = FcNAdvModuel(linear=snlinear, num_classes=num_classes)
        else:
            self.D.fc = FcNAdvModuel(linear=linear, num_classes=num_classes)

        # self.cls = nn.CrossEntropyLoss()

    def forward(self, x):
        return self.G(x)

    def training_step(self, batch, batch_idx, optimizer_idx):
        real_image, real_label = batch

        # train discriminator
        if optimizer_idx == 0:
            noise = torch.randn(real_image.size(0), 128).cuda()
            fake_image = self(noise)
            self.logger.experiment.add_images(tag="images", img_tensor=fake_image.detach().cpu(),
                                              global_step=self.current_epoch)
            real_logit = self.D(real_image)
            fake_logit = self.D(fake_image.detach())
            d_loss = d_loss_function(real_logit, fake_logit)
            return {"loss" : d_loss, "d_loss":d_loss}

        # train generator
        if optimizer_idx == 1:
            noise = torch.randn(real_image.size(0), 128).cuda()
            fake_image = self(noise)
            fake_logit = self.D(fake_image)
            g_loss = g_loss_function(fake_logit)
            return {"loss": g_loss, "g_loss":g_loss}


    def training_epoch_end(self, output):
        # for i, v in enumerate(output):
        #     print(i, v)
        d_loss = torch.stack([x[0]['loss'] for x in output]).mean()
        g_loss = torch.stack([x[1]['loss'] for x in output]).mean()
        self.log_dict({"loss/d":d_loss, "loss/g":g_loss}, logger=True)


    # def on_train_epoch_end(self):
    #     fixed_vector_output = self(self.fixed_noise)


        # pred = torch.cat([x['pred'] for x in output])
        # label = torch.cat([x['label'] for x in output])

        # self.log_dict({"loss/d":d_loss, "loss/g":g_loss})

    # def validation_step(self, batch, batch_idx):
    #     image, label = batch
    #     logit = self(image)
    #     loss = self.criterion(logit, label)
    #
    #     pred = logit.argmax(-1)
    #     cm, acc, acc_per_cls = accNaccPerCls(pred, label, self.hparams.num_class)
    #
    #     metrics = {"val_loss":loss,
    #                "val_acc": acc}
    #     metrics.update({ f"cls_{idx}" : acc for idx, acc in enumerate(acc_per_cls)})
    #
    #     self.log_dict(metrics)
    #     return metrics

    # def validation_step_end(self, val_step_outputs):
    #     # val_acc = val_step_outputs['val_acc'].cpu()
    #     # val_loss = val_step_outputs['val_loss'].cpu()
    #     #
    #     # self.log('validation_acc', val_acc, prog_bar=True)
    #     # self.log('validation_loss', val_loss, prog_bar=True)
    #     self.log_dict(val_step_outputs)
    #
    # def test_step(self, batch, batch_idx):
    #     image, label = batch
    #     logit = self(image)
    #     loss = self.criterion(logit, label)
    #
    #     pred = logit.argmax(-1)
    #     cm, acc, acc_per_cls = accNaccPerCls(pred, label, self.hparams.num_class)
    #
    #     metrics = {"test_loss":loss,
    #                "test_acc": acc}
    #     metrics.update({ f"cls_{idx}" : acc for idx, acc in enumerate(acc_per_cls)})
    #     self.log_dict(metrics)
    #     return metrics


    def configure_optimizers(self):
        d_optimizer = Adam(self.D.parameters(),
                           lr=self.hparams.learning_rate,
                           weight_decay=self.hparams.weight_decay,
                           betas=(self.hparams.beta1, self.hparams.beta2))
        g_optimizer = Adam(self.G.parameters(),
                           lr=self.hparams.learning_rate,
                           weight_decay=self.hparams.weight_decay,
                           betas=(self.hparams.beta1, self.hparams.beta2))


        return [d_optimizer, g_optimizer]

    @staticmethod
    def add_model_specific_args(parent_parser):
        parser = parent_parser.add_argument_group("model")
        parser.add_argument("--model", default='resnet18', type=str)
        parser.add_argument("--image_size", default=32, type=int)
        parser.add_argument("--image_channel", default=3, type=int)
        parser.add_argument("--std_channel", default=64, type=int)
        parser.add_argument("--latent_dim", default=128, type=int)
        parser.add_argument('--learning_rate', type=float, default=2e-4)
        parser.add_argument("--num_classes", default=10, type=int)
        parser.add_argument("--sn", default=True, type=bool)
        parser.add_argument("--bn", default=True, type=bool)
        parser.add_argument("--beta1", default=0.5, type=float)
        parser.add_argument("--beta2", default=0.9, type=float)

        parser.add_argument('--weight_decay', type=float, default=1e-5)
        return parent_parser


def cli_main():
    from argparse import ArgumentParser
    from lightning.data_module.cifar10_data_modules import  ImbalancedMNISTDataModule
    from pytorch_lightning.loggers import TensorBoardLogger
    from pytorch_lightning.strategies.ddp import DDPStrategy

    pl.seed_everything(1234)  # 다른 환경에서도 동일한 성능을 보장하기 위한 random seed 초기화

    parser = ArgumentParser()
    parser.add_argument("--augmentation", default=True, type=bool)
    parser.add_argument("--batch_size", default=128, type=int)
    parser.add_argument("--imb_factor", default=0.1, type=float)
    parser.add_argument("--balanced", default=True, type=bool)
    parser.add_argument("--retain_epoch_size", default=True, type=bool)
    parser.add_argument('--epoch', type=int, default=200)


    parser = ACGAN.add_model_specific_args(parser)
    parser = pl.Trainer.add_argparse_args(parser)

    args = parser.parse_args('')
    dm = ImbalancedMNISTDataModule.from_argparse_args(args)

    model = ACGAN(**vars(args))
    summary(model, x=torch.rand(10, 128))



    checkpoint_callback = pl.callbacks.ModelCheckpoint(filename="{epoch:d}_{loss/val:.4}_{acc/val:.4}",
        verbose=True, every_n_epochs=20
        # save_last=True,
        # save_top_k=1,
        # monitor='acc/val',
        # mode='max',
    )
    logger = TensorBoardLogger(save_dir="tb_logs",
                               name=f"acgan_cifar10_{args.imb_factor}",
                               default_hp_metric=False
                               )
    # logger.experiment.add_images()

    trainer = pl.Trainer(max_epochs=args.epoch,
                         # callbacks=[EarlyStopping(monitor='val_loss')],
                         callbacks=[checkpoint_callback],
                         # strategy=DDPStrategy(find_unused_parameters=True),
                         accelerator='gpu',
                         gpus=1,
                         logger=logger
                         )
    trainer.fit(model, datamodule=dm)

    # result = trainer.test(model, dataloaders=dm.test_dataloader())

    # print(result)


if __name__ == '__main__':
    cli_main()



