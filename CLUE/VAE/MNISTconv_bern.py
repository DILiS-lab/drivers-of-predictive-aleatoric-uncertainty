from __future__ import division
import torch
import numpy as np
from src.layers import SkipConnection
from src.utils import BaseNet, to_variable, cprint
from src.probability import normal_parse_params
import torch.nn as nn
from torch.nn import BCEWithLogitsLoss
from torch.distributions import kl_divergence
import torch.backends.cudnn as cudnn
from torch.distributions.normal import Normal
from src.radam import RAdam

class convMNIST_VAE_bern(nn.Module):
    def __init__(self, latent_dim, encoder, decoder):
        super(convMNIST_VAE_bern, self).__init__()
        self.latent_dim = latent_dim
        self.pred_sig = False

        self.encoder = encoder  # small_MNIST_recognition_net(latent_dim)
        self.decoder = decoder  # small_MNIST_generator_net(latent_dim)

        self.m_rec_loglike = BCEWithLogitsLoss(reduction='none')  # GaussianLoglike(min_sigma=1e-2)

    def encode(self, x):
        approx_post_params = self.encoder(x)
        approx_post = normal_parse_params(approx_post_params, 1e-3)
        return approx_post

    def decode(self, z_sample):
        rec_params = self.decoder(z_sample)
        return rec_params

    def vlb(self, prior, approx_post, x, rec_params):
        rec = -self.m_rec_loglike(rec_params, x).view(x.shape[0], -1).sum(-1)  # this does sum already
        kl = kl_divergence(approx_post, prior).view(x.shape[0], -1).sum(-1)
        # print(rec, kl)
        return rec - kl

    def iwlb(self, prior, approx_post, x, K=50):
        estimates = []
        for i in range(K):
            latent = approx_post.rsample()
            rec_params = self.decode(latent)
            rec_loglike = -self.m_rec_loglike(rec_params, x).view(x.shape[0], -1).sum(-1)

            prior_log_prob = prior.log_prob(latent)
            prior_log_prob = prior_log_prob.view(x.shape[0], -1)
            prior_log_prob = prior_log_prob.sum(-1)

            proposal_log_prob = approx_post.log_prob(latent)
            proposal_log_prob = proposal_log_prob.view(x.shape[0], -1)
            proposal_log_prob = proposal_log_prob.sum(-1)

            estimate = rec_loglike + prior_log_prob - proposal_log_prob
            estimates.append(estimate[:, None])

        return torch.logsumexp(torch.cat(estimates, 1), 1) - np.log(K)

class MNISTplusconv_VAE_bern_net(BaseNet):
    def __init__(self, latent_dim, encoder, decoder, lr=1e-3, cuda=True):
        super(MNISTplusconv_VAE_bern_net, self).__init__()
        cprint('y', 'VAE_bern_net')

        self.cuda = cuda

        # self.input_dim = input_dim
        # self.width = width
        # self.depth = depth
        self.latent_dim = latent_dim
        self.lr = lr

        self.create_net(encoder, decoder)
        self.create_opt()
        self.epoch = 0
        self.schedule = None

        if self.cuda:
            self.prior = self.prior = Normal(loc=torch.zeros(latent_dim).cuda(), scale=torch.ones(latent_dim).cuda())
        else:
            self.prior = Normal(loc=torch.zeros(latent_dim), scale=torch.ones(latent_dim))
        self.vlb_scale = 1 / 784  # scale for dimensions of input so we can use same LR always

    def create_net(self, encoder, decoder):
        torch.manual_seed(42)
        torch.cuda.manual_seed(42)
        self.model = convMNIST_VAE_bern(self.latent_dim, encoder, decoder)
        if self.cuda:
            self.model = self.model.cuda()
            cudnn.benchmark = True
        print('    Total params: %.2fM' % (self.get_nb_parameters() / 1000000.0))

    def create_opt(self):
        self.optimizer = RAdam(self.model.parameters(), lr=self.lr) # torch.optim.Adam

    def fit(self, x):
        self.set_mode_train(train=True)

        x, = to_variable(var=(x, ), cuda=self.cuda)
        self.optimizer.zero_grad()

        approx_post = self.model.encode(x)
        z_sample = approx_post.rsample()
        rec_params = self.model.decode(z_sample)

        vlb = self.model.vlb(self.prior, approx_post, x, rec_params)
        loss = (- vlb * self.vlb_scale).mean()

        loss.backward()
        self.optimizer.step()

        return vlb.mean().item(), torch.sigmoid(rec_params)

    def eval(self, x, sample=False):
        self.set_mode_train(train=False)

        x, = to_variable(var=(x, ), cuda=self.cuda)
        approx_post = self.model.encode(x)
        if sample:
            z_sample = approx_post.sample()
        else:
            z_sample = approx_post.loc
        rec_params = self.model.decode(z_sample)

        vlb = self.model.vlb(self.prior, approx_post, x, rec_params)

        return vlb.mean().item(), torch.sigmoid(rec_params)

    def eval_iw(self, x , k=50):
        self.set_mode_train(train=False)
        x,  = to_variable(var=(x, ), cuda=self.cuda)

        approx_post = self.model.recognition_encode(x)

        iw_lb = self.model.iwlb(self.prior, approx_post, x, k)
        return iw_lb.mean().item()

    def recongnition(self, x, grad=False):
        self.set_mode_train(train=False)
        if grad:
            if not x.requires_grad:
                x.requires_grad = True
        else:
            x, = to_variable(var=(x,), volatile=True, cuda=self.cuda)
        approx_post = self.model.encode(x)
        return approx_post

    def regenerate(self, z, grad=False):
        self.set_mode_train(train=False)
        if grad:
            if not z.requires_grad:
                z.requires_grad = True
        else:
            z, = to_variable(var=(z,), volatile=True, cuda=self.cuda)
        out = self.model.decode(z)
        if grad:
            return torch.sigmoid(out)
        else:
            return torch.sigmoid(out.data)

# import these in order to use a more general naming scheme for doodle
conv_VAE_bern = convMNIST_VAE_bern
conv_VAE_bern_net = MNISTplusconv_VAE_bern_net
