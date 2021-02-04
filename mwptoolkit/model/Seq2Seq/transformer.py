import torch
from torch import nn

from mwptoolkit.module.Encoder.transformer_encoder import TransformerEncoder
from mwptoolkit.module.Decoder.transformer_decoder import TransformerDecoder
from mwptoolkit.module.Embedder.position_embedder import PositionEmbedder
from mwptoolkit.module.Embedder.basic_embedder import BaiscEmbedder
from mwptoolkit.module.Attention.self_attention import SelfAttentionMask
from mwptoolkit.module.Strategy.beam_search import Beam_Search_Hypothesis
from mwptoolkit.module.Strategy.sampling import topk_sampling
from mwptoolkit.module.Strategy.greedy import greedy_search

class Transformer(nn.Module):
    def __init__(self,config):
        super().__init__()
        self.max_output_len=config["max_output_len"]
        self.share_vocab=config["share_vocab"]
        self.decoding_strategy=config["decoding_strategy"]
        
        self.in_pad_idx=config["in_word2idx"]["<PAD>"]
        if config["share_vocab"]:
            self.out_symbol2idx=config["out_symbol2idx"]
            self.out_idx2symbol=config["out_idx2symbol"]
            self.in_word2idx=config["in_word2idx"]
            self.in_idx2word=config["in_idx2word"]
            self.out_pad_idx=self.in_pad_idx
            self.out_sos_idx=config["in_word2idx"]["<SOS>"]
        else:
            self.out_pad_idx=config["out_symbol2idx"]["<PAD>"]
            self.out_sos_idx=config["out_symbol2idx"]["<SOS>"]

        self.in_embedder=BaiscEmbedder(config["vocab_size"],config["embedding_size"],config["embedding_dropout_ratio"])
        if config["share_vocab"]:
            self.out_embedder=self.in_embedder
        else:
            self.out_embedder=BaiscEmbedder(config["symbol_size"],config["embedding_size"],config["embedding_dropout_ratio"])
        
        self.pos_embedder=PositionEmbedder(config["embedding_size"],config["device"],config["embedding_dropout_ratio"],config["max_len"])
        self.self_attentioner=SelfAttentionMask()
        self.encoder=TransformerEncoder(config["embedding_size"],config["ffn_size"],config["num_encoder_layers"],\
                                            config["num_heads"],config["attn_dropout_ratio"],\
                                            config["attn_weight_dropout_ratio"],config["ffn_dropout_ratio"])
        self.decoder=TransformerDecoder(config["embedding_size"],config["ffn_size"],config["num_decoder_layers"],\
                                            config["num_heads"],config["attn_dropout_ratio"],\
                                            config["attn_weight_dropout_ratio"],config["ffn_dropout_ratio"])
        self.out=nn.Linear(config["embedding_size"],config["symbol_size"])
    
    def forward(self,src,target=None):
        source_embeddings = self.pos_embedder(self.in_embedder(src))
        source_padding_mask = torch.eq(src, self.in_pad_idx)
        encoder_outputs = self.encoder(source_embeddings,
                                       self_padding_mask=source_padding_mask)

        if target != None:
            token_logits=self.generate_t(target,encoder_outputs,source_padding_mask)
            return token_logits
        else:
            all_outputs=self.generate_without_t(encoder_outputs,source_padding_mask)
            return all_outputs
    
    def generate_t(self,target,encoder_outputs,source_padding_mask):
        batch_size=encoder_outputs.size(0)
        device=encoder_outputs.device
        input_seq = torch.LongTensor([self.out_sos_idx]*batch_size).view(batch_size,-1).to(device)
        target=torch.cat((input_seq,target),dim=1)[:,:-1]

        decoder_inputs = self.pos_embedder(self.out_embedder(target))
        self_padding_mask = torch.eq(target, self.out_pad_idx)
        self_attn_mask = self.self_attentioner(target.size(-1)).bool()
        decoder_outputs = self.decoder(decoder_inputs,
                                       self_padding_mask=self_padding_mask,
                                       self_attn_mask=self_attn_mask,
                                       external_states=encoder_outputs,
                                       external_padding_mask=source_padding_mask)
        token_logits = self.out(decoder_outputs)
        token_logits=token_logits.view(-1, token_logits.size(-1))
        return token_logits
    def generate_without_t(self,encoder_outputs,source_padding_mask):
        batch_size=encoder_outputs.size(0)
        device=encoder_outputs.device
        input_seq = torch.LongTensor([self.out_sos_idx]*batch_size).view(batch_size,-1).to(device)
        all_outputs=[]
        for gen_idx in range(self.max_output_len):
            self_attn_mask = self.self_attentioner(input_seq.size(-1)).bool()
            #decoder_input = self.out_embedder(input_seq) + self.pos_embedder(input_seq)
            decoder_input = self.pos_embedder(self.out_embedder(input_seq))
            decoder_outputs = self.decoder(decoder_input, 
                                            self_attn_mask=self_attn_mask,
                                            external_states=encoder_outputs, 
                                            external_padding_mask=source_padding_mask)

            token_logits = self.out(decoder_outputs[:, -1, :].unsqueeze(1))
            if self.decoding_strategy=="topk_sampling":
                output=topk_sampling(token_logits,top_k=5)
            elif self.decoding_strategy=="greedy_search":
                output=greedy_search(token_logits)
            else:
                raise NotImplementedError
            all_outputs.append(output)
            if self.share_vocab:
                input_seq=self.decode(output)
            else:
                input_seq=output
        all_outputs=torch.cat(all_outputs,dim=1)
        return all_outputs
    def decode(self,output):
        device=output.device

        batch_size=output.size(0)
        decoded_output=[]
        for idx in range(batch_size):
            decoded_output.append(self.in_word2idx[self.out_idx2symbol[output[idx]]])
        decoded_output=torch.tensor(decoded_output).to(device).view(batch_size,-1)
        return output