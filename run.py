#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Dec 23 09:26:33 2019

@author: YuxuanLong
"""

import numpy as np
import torch
import utils
import torch.optim as optim
import torch.nn as nn
import os

# Run on GPU if CUDA is available
RUN_ON_GPU = torch.cuda.is_available()

# Set random seeds
SEED = 2019
np.random.seed(SEED)
torch.manual_seed(SEED)
if RUN_ON_GPU:
    torch.cuda.manual_seed(SEED)

def data_whitening(x, epsilon = 1e-9):
    """
    Perform ZCA for data whitening on the features.
    
    Return:
        M       the linear transformation matrix
        mean    the mean of the feature
    """
    mean = np.mean(x, axis = 0)
    x_norm = x - mean
    sigma = np.dot(x_norm.T, x_norm) / x.shape[0]
    u, V = np.linalg.eig(sigma)
    M = np.dot(V / np.sqrt(u + epsilon), V.T)
    return M, mean


if __name__ == '__main__':
    train_flag = True
    test_flag = True
    
    rate_num = 5
    use_side = False
    lr = 1e-2 # 1e-2
    weight_decay = 1e-5
    num_epochs = 1000 # 1000
    hidden_dim = 5 # 100
    side_hidden_dim = 5 # 10
    out_dim = 5 # 75
    drop_out = 0.0
    split_ratio = 0.8
    save_period = 100
    verbal_period = 100
    
    ### Rating matrix loading, processing, split
    user_item_matrix = np.load('./processed_dataset/user_item_matrix.npy')
    num_user, num_item = user_item_matrix.shape
    mask = user_item_matrix > 0
    mask_new = mask + np.random.uniform(0, 1, (num_user, num_item))
    train_mask = (mask_new <= (1 + split_ratio)) & mask
    test_mask = (mask_new > (1 + split_ratio)) & mask
    user_item_matrix_train = user_item_matrix + 0
    user_item_matrix_train[test_mask] = 0
    user_item_matrix_test = user_item_matrix + 0
    user_item_matrix_test[train_mask] = 0
    np.save('./processed_dataset/user_item_matrix_train.npy', user_item_matrix_train)
    np.save('./processed_dataset/user_item_matrix_test.npy', user_item_matrix_test)
    all_M_u = []
    all_M_v = []
    all_M = []
    for i in range(rate_num):
        M_r = user_item_matrix_train == (i + 1)
        all_M_u.append(utils.normalize(M_r))
        all_M_v.append(utils.normalize(M_r.T))
        all_M.append(M_r)
    all_M = np.array(all_M)
    mask = user_item_matrix_train > 0   
    
    
    ### side feature loading and processing
    raw_side_feature_u = np.load('./processed_dataset/user_data_np.npy', allow_pickle = True)
    raw_side_feature_v = np.load('./processed_dataset/item_data_np.npy', allow_pickle = True)
    
    M_u, mean_u = data_whitening(raw_side_feature_u)
    M_v, mean_v = data_whitening(raw_side_feature_v)
    
    side_feature_u = np.dot(raw_side_feature_u - mean_u, M_u)
    side_feature_v = np.dot(raw_side_feature_v - mean_v, M_v)
    
    
    ### input feature generation
    feature_dim = num_user + num_item
    I = np.eye(num_user + num_item)
    feature_u = I[0:num_user, :]
    feature_v = I[num_user:, :]
    
    if train_flag:
        if not os.path.exists('./parameters'):
            os.makedirs('./parameters')  
        weights_name = './parameters/weights'
        
    
        net = utils.create_models(feature_u, feature_v, feature_dim, hidden_dim, rate_num, all_M_u, all_M_v, 
                     side_hidden_dim, side_feature_u, side_feature_v, use_side, out_dim, drop_out)
        net.train() # in train mode
    
        # create AMSGrad optimizer
        optimizer = optim.Adam(net.parameters(), lr = lr, weight_decay = weight_decay)
        Loss = utils.loss(all_M, mask, user_item_matrix_train)
    
        for epoch in range(num_epochs):
            
            optimizer.zero_grad()
    
            score = net.forward()
    
            loss = Loss.loss(score)
            
            loss.backward()
            
            optimizer.step()
    #        print('Loss: ', loss.data.item())
            
            
            if epoch % verbal_period == 0:
                print('Start epoch ', epoch)
                epoch_loss = loss.data.item()
                print('Loss: ', epoch_loss)
                
            if epoch % save_period == 0:
                with torch.no_grad():
                    rmse = Loss.rmse(score)
                    print('Training RMSE: ', rmse.data.item())        
                                    
                    torch.save(net.state_dict(), weights_name)
    
        rmse = Loss.rmse(score)
        print('Final training RMSE: ', rmse.data.item())        
        torch.save(net.state_dict(), weights_name)

        sm = nn.Softmax(dim = 0)
        score = sm(score)
        score_list = torch.split(score, rate_num)
        pred = 0
        for i in range(rate_num):
            pred += (i + 1) * score_list[0][i]
    
        pred = utils.var_to_np(pred)
        np.save('./prediction.npy', pred)
    
    ### test
    if test_flag:
        pred = np.load('./prediction.npy')
        
        test_mask = user_item_matrix_test > 0
        
        square_err = (pred * test_mask - user_item_matrix_test) ** 2
        mse = square_err.sum() / test_mask.sum()
        test_rmse = np.sqrt(mse)
        print('Test RMSE: ', test_rmse)