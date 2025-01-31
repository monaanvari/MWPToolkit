from mwptoolkit.utils.enum_type import FixType, SpecialTokens
import torch
import random
# -*- encoding: utf-8 -*-
# @Author: Yihuai Lan
# @Time: 2021/08/18 11:34:06
# @File: abstract_dataloader.py


class AbstractDataLoader(object):
    """abstract dataloader

    the base class of dataloader class
    """

    def __init__(self, config, dataset):
        """
        Args:
            config (mwptoolkit.config.configuration.Config)

            dataset (mwptoolit.data.dataset)

        expected that config includes these parameters below:

        model (str): model name.

        equation_fix (str): [infix | postfix | prefix], convert equation to specified format.

        train_batch_size (int): the training batch size.

        test_batch_size (int): the testing batch size.

        symbol_for_tree (bool): build output symbols for tree or not.

        share_vocab (bool): encoder and decoder of the model share the same vocabulary, often seen in Seq2Seq models.

        max_len (int|None): max input length.

        add_sos (bool): add sos token at the head of input sequence.

        add_eos (bool): add eos token at the tail of input sequence.
        """
        super().__init__()
        self.model = config["model"]
        self.equation_fix = config["equation_fix"]
        self.train_batch_size = config["train_batch_size"]
        self.test_batch_size = config["test_batch_size"]
        self.symbol_for_tree = config["symbol_for_tree"]
        self.share_vocab = config["share_vocab"]

        self.max_len = config["max_len"]
        self.max_equ_len = config["max_equ_len"]
        self.add_sos = config["add_sos"]
        self.add_eos = config["add_eos"]
        self.filt_dirty = config["filt_dirty"]

        self.device = config["device"]

        self.dataset = dataset
        self.in_pad_token = None
        self.in_unk_token = None

        self.out_pad_token = None
        self.out_unk_token = None
        self.temp_unk_token = None
        self.temp_pad_token = None

    def _pad_input_batch(self, batch_seq, batch_seq_len):
        if self.max_len != None:
            max_length = self.max_len
        else:
            max_length = max(batch_seq_len)
        for idx, length in enumerate(batch_seq_len):
            if length < max_length:
                batch_seq[idx] += [
                    self.in_pad_token for i in range(max_length - length)]
            else:
                if self.add_sos and self.add_eos:
                    batch_seq[idx] = [batch_seq[idx][0]] + \
                        batch_seq[idx][1:max_length-1] + [batch_seq[idx][-1]]
                else:
                    batch_seq[idx] = batch_seq[idx][:max_length]
        return batch_seq

    def _pad_output_batch(self, batch_target, batch_target_len):
        if self.max_equ_len != None:
            max_length = self.max_equ_len
        else:
            max_length = max(batch_target_len)
        for idx, length in enumerate(batch_target_len):
            if length < max_length:
                batch_target[idx] += [
                    self.out_pad_token for i in range(max_length - length)]
            else:
                batch_target[idx] = batch_target[idx][:max_length]
        return batch_target

    def _word2idx(self, sentence):
        sentence_idx = []
        for word in sentence:
            try:
                idx = self.dataset.in_word2idx[word]
            except:
                idx = self.in_unk_token
            sentence_idx.append(idx)
        return sentence_idx

    def _equ_symbol2idx(self, equation):
        equ_idx = []
        if self.equation_fix == FixType.MultiWayTree:
            for symbol in equation:
                if isinstance(symbol, list):
                    sub_equ_idx = self._equ_symbol2idx(symbol)
                    equ_idx.append(sub_equ_idx)
                else:
                    if self.share_vocab:
                        try:
                            idx = self.dataset.in_word2idx[symbol]
                        except:
                            idx = self.in_unk_token
                    else:
                        try:
                            idx = self.dataset.out_symbol2idx[symbol]
                        except:
                            idx = self.out_unk_token
                    equ_idx.append(idx)
        else:
            for word in equation:
                if self.share_vocab:
                    try:
                        idx = self.dataset.in_word2idx[word]
                    except:
                        idx = self.in_unk_token
                else:
                    try:
                        idx = self.dataset.out_symbol2idx[word]
                    except:
                        idx = self.out_unk_token
                equ_idx.append(idx)
        return equ_idx

    def _temp_symbol2idx(self, template):
        temp_idx = []
        if self.equation_fix == FixType.MultiWayTree:
            for symbol in template:
                if isinstance(symbol, list):
                    sub_equ_idx = self._equ_symbol2idx(symbol)
                    temp_idx.append(sub_equ_idx)
                else:
                    if self.share_vocab:
                        try:
                            idx = self.dataset.in_word2idx[symbol]
                        except:
                            idx = self.in_unk_token
                    else:
                        try:
                            idx = self.dataset.temp_symbol2idx[symbol]
                        except:
                            idx = self.out_unk_token
                    temp_idx.append(idx)
        else:
            for word in template:
                if self.share_vocab:
                    try:
                        idx = self.dataset.in_word2idx[word]
                    except:
                        idx = self.in_unk_token
                else:
                    try:
                        idx = self.dataset.temp_symbol2idx[word]
                    except:
                        idx = self.temp_unk_token
                temp_idx.append(idx)
        return temp_idx

    def _get_mask(self, batch_seq_len):
        max_length = max(batch_seq_len)
        batch_mask = []
        for idx, length in enumerate(batch_seq_len):
            batch_mask.append([1] * length + [0] * (max_length - length))
        return batch_mask

    def _get_input_mask(self, batch_seq_len):
        if self.max_len:
            max_length = self.max_len
        else:
            max_length = max(batch_seq_len)
        batch_mask = []
        for idx, length in enumerate(batch_seq_len):
            batch_mask.append([1] * length + [0] * (max_length - length))
        return batch_mask

    def _build_num_stack(self, equation, num_list):
        num_stack = []
        for word in equation:
            temp_num = []
            flag_not = True
            if word not in self.dataset.out_idx2symbol:
                flag_not = False
                if "NUM" in word:
                    temp_num.append(int(word[4:]))
                for i, j in enumerate(num_list):
                    if j == word:
                        temp_num.append(i)

            if not flag_not and len(temp_num) != 0:
                num_stack.append(temp_num)
            if not flag_not and len(temp_num) == 0:
                num_stack.append([_ for _ in range(len(num_list))])
        num_stack.reverse()
        return num_stack

    def load_data(self):
        """load data.
        """
        raise NotImplementedError
