from __future__ import unicode_literals
import configargparse
from onmt.utils.logging import init_logger
from onmt.utils.misc import split_corpus
from onmt.translate.translator import build_translator
from bert_eojeol_pytorch.src_tokenizer import tokenization
import nltk
import onmt.opts as opts
import torch
import copy
import os
import sys

tokenizer = tokenization.BertTokenizer('./modules/multi_summ/bert_eojeol_pytorch/vocab.korean.rawtext.list')

class mds():
    def __init__(self, gpu):
        parser = configargparse.ArgumentParser(
            description='translate.py',
            config_file_parser_class=configargparse.YAMLConfigFileParser,
            formatter_class=configargparse.ArgumentDefaultsHelpFormatter)
        opts.config_opts(parser)
        opts.add_md_help_argument(parser)
        opts.translate_opts(parser)
        os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
        if len(gpu) > 1:
            print('do not try hacking')
            exit()
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
        
        sys.argv = ["python"]
        opt = parser.parse_args()

        opt.models = ['./modules/multi_summ/dataset_m2s2/korean_bert_8_single_new_economy_add_cls_sep_segment_eos_penalty_new_bloom_step_25000.pt']
        opt.segment = True
        opt.batch_size = 8
        opt.beam_size = 10
        opt.src = '.1'
        opt.output = '.1'
        opt.verbose = True
        opt.stepwise_penalty = True
        opt.coverage_penalty = 'sumarry'
        opt.beta = 5
        opt.length_penalty = 'wu'
        opt.alpha = 0.9
        opt.block_ngram_repeat = 3
        opt.ignore_when_blocking = [".", "</t", "<t>", ",_", "%"]
        opt.max_length = 300
        opt.min_length = 35
        opt.gpu = 0
        opt.segment=True

        logger = init_logger(opt.log_file)
        self.translator = build_translator(opt, report_score=True)
        
    def m_translate(self, srcs):
        '''
        :param srcs: [str, str, ..., ]
        :return: str 
        '''
        raw_src = [['[CLS]'] + tokenizer.tokenize(src) for src in srcs]
        src = [tokenizer.convert_tokens_to_ids(rs[:512]) for rs in raw_src]
        src_lengths = torch.tensor([len(a) for a in src])
        max_len = min(512, max(src_lengths))
        src_lengths, indices = src_lengths.sort(descending=True)
        src = torch.tensor([a + [0 for _ in range(max_len - len(a))] for a in src])[indices]
        itos = []
        stoi = {}
        i = 0
        for w in [a for b in raw_src for a in b]:
            try:
                stoi[w]
            except KeyError:
                stoi[w] = i
                itos.append(w)
                i += 1
        src_map = []
        for a in src:
            for b in a:
                if int(b) != 0:
                    src_map.append(stoi[tokenizer.ids_to_tokens[int(b)]])
        src_map = torch.tensor(src_map).view(1, -1)
        data_iter = [{'raw_src': raw_src, 'src': src.transpose(0, 1).to('cuda'), 'indices': indices, 'src_map': src_map.to('cuda'), 'itos': itos, 'stoi': stoi, 'src_lengths': src_lengths.to('cuda')}]

        translations = self.translator.translate(src=[' '.join(raw_src[0]).encode('utf-8')], tgt=None, src_dir='', batch_size=1, attn_debug=False, data_iter=data_iter)
        if translations[0].pred_sents[0][-1] == '._' and translations[0].pred_sents[0][-2] == '._':
            tgt = ' '.join([sln for sln in nltk.sent_tokenize(' '.join(translations[0].pred_sents[0]).replace(' ', '').replace('_', ' ')) if sln != '._'])
        else:
            tgt = ' '.join(translations[0].pred_sents[0]).replace(' ', '').replace('_', ' ')
        
        return tgt
