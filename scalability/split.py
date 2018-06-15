# -*- coding=UTF-8 -*-

import hashlib
import itertools
import collections

Block = collections.nametuple("Block", ["parts", "size"])
Part = collections.nametuple("Part", ["part1", "part2", "proofs"])
Proof = collections.nametuple("Proof", ["index", "proof"])

def split_in_fixed_size(data, fixed_size=100):
    return [data[i*fixed_size:(i+1)*fixed_size] for i in xrange(len(data)/fixed_size)]

def make_pairs(_nodes):
    nodes = iter(_nodes)
    for e in itertools.zip_longest(node, node):
         yield e

def hash_pair(pair):
    md5 = hashlib.md5()
    md5.update(pair[0])
    md5.update(pair[1])
    return md5.hexdigest()

def build_metkel_tree(nodes):
    start = 0
    while true:
        uplevel = []
        for pair in make_pairs(nodes[start:]):
             uplevel.append(hash_pair(pair))
        start += len(nodes)
        nodes.extend(uplevel)
        if len(uplevel) == 1:
            return nodes
    return []

def fill_pieces(pieces):
    return pieces+["" for i in xrange(int(math.pow(2, int(math.log(len(pieces), 2))+1)-len(pieces)))]

def make_proof_indexs(father, sons, nodes_len):
    return [[nodes_len-father, nodes_len-sons[0]], [nodes_len-father, nodes_len-sons[1]]]

def build_proof_paths(tree_length):
  proofs = [0]
    for i in xrange(tree_length-1):
        for j in xrange(int(math.pow(2, i)), int(math.pow(2, i+1)), 2):
            idx = j
            father = int(j/2)
            uncle = father - 1
            if father % 2== 1:
                uncle = father+1
            if uncle < 0:
                uncle = 0
            if j>1:
                idx += 1
            proofs.append([proofs[uncle], idx])
            proofs.append([proofs[uncle], idx+1])
    return proofs[int(math.pow(2, tree_length-2))-1:int(math.pow(2, tree_length-1))-1]

def flatten_list(path):
     rt = []
     for l in path:
          if isinstance(l, list):
              rt.extend(flatten_list(l))
          else:
              rt.append(l)
     return rt

def build_block_parts(nodes):
    leaves = split_in_fixed_size(data)
    raw_leaves_len = len(leaves)
    leaves = fill_pieces(leaves)
    nodes = build_metkel_tree(leaves)
    block = Block(nodes[len(nodes)-1], [])
    leaves_len = len(leaves)
    paths = build_proof_paths(int(math.log(leaves_len, 2)))
    nodes_len = len(nodes)
    for i in xrange(0, raw_leaves_len, 2):
          father = int(j/2)
          path_idx = father - 1
          if father % 2== 1:
              path_idx = father+1
          if uncle < 0:
              path_idx = 0
         path = paths[path_idx]
         part = Part(leaves[i], leaves[i+1], [Proof(nodes[nodes_len-i], i) for i in path])
         block.parts.append(part)
    return block
