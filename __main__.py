#!/usr/bin/env python3

import argparse
import os
from lxml import etree
from itertools import zip_longest
from funcy import collecting
from tqdm import tqdm
import json
import re
import fnmatch

NSMAP = {'fb2': 'http://www.gribuser.ru/xml/fictionbook/2.0'}
MAX_PATH_DEPTH = 128

def parse_args():
    p = argparse.ArgumentParser(description='tool to rename fb2 files')
    p.add_argument('--path', help='path to file or folder with files')
    p.add_argument('--config')
    p.add_argument('-n', action='store_true')
    return p.parse_args()


def get_node(root, *args):
    xpath = '/'.join(f'fb2:{e}' for e in args)
    nodes = root.xpath(f'//{xpath}', namespaces=NSMAP)
    return [n.text for n in nodes if n.text]


@collecting
def get_authors(title_info):
    for last, first in zip_longest(
        get_node(title_info, 'author', 'last-name'),
        get_node(title_info, 'author', 'first-name'),
    ):
        if first and last:
            yield f'{last} {first}'


SANITIZE_REGEXS = [
    re.compile('^\d+\)'),
    re.compile('[^а-яА-Яa-zA-Z0-9 \.,-]'),
]

def clean_string(s):
    if not s:
        return '', False

    if isinstance(s, list):
        s = s[0]

    new_s = s.strip()
    for r in SANITIZE_REGEXS:
        new_s = re.sub(r, '', new_s)
    new_s = new_s.strip()

    return new_s, s != new_s


def file_info(path, pattern):
    try:
        tree = etree.parse(path)
    except etree.XMLSyntaxError as e:
        return {'path': path, 'broken': e}

    title_info = tree.getroot().xpath('//fb2:description/fb2:title-info', namespaces=NSMAP)[0]

    modified = False

    titles_raw = get_node(title_info, 'book-title')
    title, titles_modified = clean_string(titles_raw)
    modified = modified or titles_modified

    authors_raw = get_authors(title_info)
    author, authors_modified = clean_string(authors_raw)
    modified = modified or authors_modified

    modified = modified or len(titles_raw) != 1 or len(authors_raw) != 1
    new_name = pattern.format(author=author, title=title)
    return {
        'name': new_name,
        # 'full': repr(authors_raw) + " | " + repr(titles_raw),
        # 'modified': modified,
        'path': path,
        'broken': 'empty name' if not new_name else None
    }


def get_files(root, relpath='', file_name='', depth=0):
    if depth >= MAX_PATH_DEPTH:
        raise Exception(f'Too deep path {relpath}')
    full_path = os.path.join(root, relpath) if relpath else root
    full_file_path = os.path.join(full_path, file_name)

    if os.path.isfile(full_file_path) and full_file_path.endswith('.fb2'):
        yield relpath, full_path, full_file_path

    if os.path.isdir(full_file_path):
        for fname in os.listdir(full_file_path):
            yield from get_files(root, os.path.join(relpath, file_name), fname, depth=depth + 1)


def load_config(path):
    if path is None and os.path.isfile('config.json'):
        path = 'config.json'
    if path:
        with open(path, 'r') as cfg_file:
            return json.load(cfg_file)
    return {'patterns': []}


def get_pattern(relpath, config):
    for path_pattern, name_pattern in config['patterns']:
        if fnmatch.fnmatch(relpath, path_pattern):
            return name_pattern
    return '{author} - {title}'


def main(args):
    config = load_config(args.config)
    for relpath, full_path, full_file_path in tqdm(get_files(args.path)):
        fname_pattern = get_pattern(relpath, config)
        row = file_info(full_file_path, fname_pattern)
        if row['broken']:
            print(row)
            continue
        new_path = os.path.join(full_path, row['name']) + '.fb2'
        if args.n:
            if full_file_path != new_path:
                print('> ', full_file_path, ' -> ', new_path)
        else:
            os.rename(full_file_path, new_path)


if __name__ == '__main__':
    args = parse_args()
    main(args)
