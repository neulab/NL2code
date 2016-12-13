import numpy as np
import cProfile
import ast
import traceback
import argparse
import os
import logging
from vprof import profiler

from model import Model
from dataset import DataEntry, DataSet, Vocab, Action
import config
from learner import Learner
from evaluation import *
from decoder import decode_python_dataset
from components import Hyp
from astnode import ASTNode

from nn.utils.generic_utils import init_logging
from nn.utils.io_utils import deserialize_from_file, serialize_to_file

parser = argparse.ArgumentParser()
sub_parsers = parser.add_subparsers(dest='operation')
train_parser = sub_parsers.add_parser('train')
decode_parser = sub_parsers.add_parser('decode')
interactive_parser = sub_parsers.add_parser('interactive')
evaluate_parser = sub_parsers.add_parser('evaluate')

def parse_args():
    parser.add_argument('-data')
    parser.add_argument('-model', default=None)
    parser.add_argument('-conf', default='config.py', help='config file name')

    decode_parser.add_argument('-saveto', default='decode_results.bin')
    decode_parser.add_argument('-type', default='test_data')

    evaluate_parser.add_argument('-input', default='decode_results.bin')
    evaluate_parser.add_argument('-type', default='test_data')

    interactive_parser.add_argument('-mode', default='dataset')

    args = parser.parse_args()

    return args

if __name__ == '__main__':
    init_logging('parser.log', logging.INFO)
    args = parse_args()

    logging.info('current config: %s', config_info)

    np.random.seed(181783)

    dataset_file = 'data/django.cleaned.dataset.freq5.bin'

    if args.data:
        dataset_file = args.data


    logging.info('loading dataset [%s]', dataset_file)
    train_data, dev_data, test_data = deserialize_from_file(dataset_file)

    # # get action steps statistics
    # avg_action_num = np.average([len(e.actions) for e in train_data.examples])
    # logging.info('avg_action_num: %d', avg_action_num)

    logging.info('source vocab size: %d', train_data.annot_vocab.size)
    logging.info('target vocab size: %d', train_data.terminal_vocab.size)

    if args.operation in ['train', 'decode', 'interactive']:
        model = Model()
        model.build()

        if args.model:
            model.load(args.model)

    if args.operation == 'train':
        # train_data = train_data.get_dataset_by_ids(range(200), 'train_sample')
        # dev_data = dev_data.get_dataset_by_ids(range(10), 'dev_sample')
        learner = Learner(model, train_data, dev_data)
        learner.train()

    if args.operation == 'decode':
        # ==========================
        # investigate short examples
        # ==========================

        # short_examples = [e for e in test_data.examples if e.parse_tree.size <= 2]
        # for e in short_examples:
        #     print e.parse_tree
        # print 'short examples num: ', len(short_examples)

        # dataset = test_data # test_data.get_dataset_by_ids([1,2,3,4,5,6,7,8,9,10], name='sample')
        # cProfile.run('decode_dataset(model, dataset)', sort=2)

        # from evaluation import decode_and_evaluate_ifttt
        # decode_and_evaluate_ifttt(model, test_data)
        # exit(0)

        dataset = eval(args.type)
        decode_results = decode_python_dataset(model, dataset)
        serialize_to_file(decode_results, args.saveto)

    if args.operation == 'evaluate':
        decode_results_file = args.input
        dataset = eval(args.type)
        decode_results = deserialize_from_file(decode_results_file)

        evaluate_decode_results(dataset, decode_results)

    if args.operation == 'interactive':
        from dataset import canonicalize_query, query_to_data
        from collections import namedtuple
        from lang.py.parse import decode_tree_to_python_ast
        assert model is not None

        while True:
            cmd = raw_input('example id or query: ')
            if args.mode == 'dataset':
                try:
                    example_id = int(cmd)
                    example = [e for e in test_data.examples if e.raw_id == example_id][0]
                except:
                    print 'something went wrong ...'
                    continue
            elif args.mode == 'new':
                # we play with new examples!
                query, str_map = canonicalize_query(cmd)
                vocab = train_data.annot_vocab
                query_tokens = query.split(' ')
                query_tokens_data = [query_to_data(query, vocab)]
                example = namedtuple('example', ['query', 'data'])(query=query_tokens, data=query_tokens_data)

            if hasattr(example, 'parse_tree'):
                print 'gold parse tree:'
                print example.parse_tree

            cand_list = model.decode(example, train_data.grammar, train_data.terminal_vocab,
                                     beam_size=BEAM_SIZE, max_time_step=DECODE_MAX_TIME_STEP)

            for cid, cand in enumerate(cand_list[:10]):
                print '*' * 60
                print 'cand #%d, score: %f' % (cid, cand.score)

                try:
                    ast_tree = decode_tree_to_python_ast(cand.tree)
                    code = astor.to_source(ast_tree)
                    print 'code: ', code
                except:
                    print "Exception in converting tree to code:"
                    print '-' * 60
                    print 'raw_id: %d, beam pos: %d' % (example.raw_id, cid)
                    traceback.print_exc(file=sys.stdout)
                    print '-' * 60
                finally:
                    print cand.tree.__repr__()
                    print 'n_timestep: %d' % cand.n_timestep
                    print 'ast size: %d' % cand.tree.size
                    print '*' * 60
