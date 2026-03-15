#!/user/bin/env python
# -*- coding: utf-8 -*-
# Time: 2026/3/15 23:19
# Author: chonmb
# Software: PyCharm
import itertools
import os
import re


class Block:
    md_empty_line = ''
    start_target = None
    end_target = None

    def match(self, line, lines_iter):
        if re.match(f'^{self.start_target}(.*?)$', line):
            return True
        else:
            return False

    def parse(self, line, lines_iter):
        return re.findall(f'^{self.start_target}(.*?)$', line)[0]

    def dumps(self, header, body):
        return f'{self.start_target}{header}'


class TitleBlock1(Block):
    start_target = r'# '


class TitleBlock2(Block):
    start_target = r'## '

class TitleBlock3(Block):
    start_target = r'### '


class ListBlock(Block):
    start_target = r'- '

    def parse(self, line, lines_iter):
        list_content = [re.findall(f'^{self.start_target}(.*?)$', line)[0]]

        while re.match(f'^{self.start_target}(.*?)$', lines_iter.peek_next()):
            list_content.append(re.findall(f'^{self.start_target}(.*?)$', next(lines_iter))[0])

        return '', list_content

    def dumps(self, header, body):
        return '\n'.join(['-' + b for b in body])


class TableBlock(Block):
    start_target = '\|'
    table_header_regex = r'\|.*?\|$'
    table_split_regex = r'^\|\s*[-\|:]+\s*\|$'
    table_body_regex = table_header_regex
    table_column_regex = r'\|\s*([^|]+?)\s*(?=\|)'

    def match(self, line, lines_iter):
        iters = lines_iter.peek_iterator()
        if re.match(self.table_header_regex, line):
            table_split_line = next(iters)
            if not re.match(self.table_split_regex, table_split_line):
                print(table_split_line)
                return False
            for body_line in iters:
                if not body_line:
                    return True
                elif re.match(self.table_body_regex, body_line):
                    continue
                else:
                    return False
        return False

    def parse(self, line, lines_iter):
        headers = re.findall(self.table_column_regex, line)
        next(lines_iter)
        body = []
        if not lines_iter.peek_next():
            return headers, body

        for body_line in lines_iter:
            row = re.findall(self.table_column_regex, body_line)
            body.append(row)
            if not lines_iter.peek_next():
                break
        return headers, body

    def dumps(self, header, body):
        return '\n'.join([
            f'|{"|".join([f" {h} " for h in header])}|',
            '| --- ' * len(header) + '|',
            *[f'|{"|".join([f" {c} " for c in r])}|' for r in body]
        ])


class CodeBlock(Block):
    start_target = '```'
    end_target = '```'

    def match(self, line, lines_iter):
        iters = lines_iter.peek_iterator()
        if re.match(f'^{self.start_target}(.*?)$', line):
            for next_lines in iters:
                if re.match(f'^{self.end_target}.*?$', next_lines):
                    return True
        return False

    def parse(self, line, lines_iter):
        code_type = re.findall(f'^{self.start_target}(.*?)$', line)[0]
        codes = []
        for next_lines in lines_iter:
            if re.match(f'^{self.end_target}.*?$', next_lines):
                return code_type, codes
            codes.append(next_lines)
        return code_type, codes

    def dumps(self, header, body):
        return '```{}\n{}\n```'.format(header, "\n".join(body))


class ParagraphBlock(Block):
    start_target = '[\s\S]+'

    def parse(self, line, lines_iter):
        return '', line

    def dumps(self, header, body):
        return '\n'.join(body)


class EmptyBlock(Block):
    start_target = ''


match_block_map = {block_type: block_type() for block_type in Block.__subclasses__()}


class MarkdownIterator:
    def __init__(self, text: str):
        self.text = text
        self.lines = text.splitlines()
        self.index = -1

    def peek_iterator(self):
        if self.index + 1 >= len(self.lines):
            return None
        return iter(self.lines[self.index + 1:])

    def peek_next(self):
        if self.index >= len(self.lines):
            return None
        else:
            return self.lines[self.index + 1]

    def __iter__(self):
        return self

    def __next__(self):
        self.index += 1
        if self.index >= len(self.lines):
            raise StopIteration
        return self.lines[self.index]


class BlockStruct:
    def __init__(self, block: type, header=None, body=None):
        self.block = block
        self.header = header
        self.body = []
        if body is not None:
            if isinstance(body, list):
                self.body.extend(body)
            else:
                self.body.append(body)

    def __repr__(self):
        return str(self)

    def __str__(self):
        if self.header:
            return f'[{self.block.__name__}] ({self.header}, {self.body})'
        return f'[{self.block.__name__}] ({self.body})'


def parse_block(line, line_iter):
    for k, v in match_block_map.items():
        if v.match(line, line_iter):
            r = v.parse(line, line_iter)
            if isinstance(r, tuple):
                header, body = r[0], r[1]
                block = BlockStruct(k, header=header, body=body)
            else:
                block = BlockStruct(k, header=r)
            return block
    return BlockStruct(EmptyBlock, header='')


class MarkdownContext:
    def __init__(self, path: str = None, mode: str = 'r', text: str = None):
        self.path = path
        self.mode = mode
        self.text = text
        self.blocks = []
        self.cursor = None
        self.file = None

    def table(self, columns: list, *rows: list):
        self.blocks.insert(self.cursor, BlockStruct(TableBlock, header=columns, body=list(rows)))
        self.cursor += 1

    def code(self, code_type: str, *codes: str):
        self.blocks.insert(self.cursor, BlockStruct(CodeBlock, header=code_type, body=list(codes)))
        self.cursor += 1

    def list(self, *lists: str):
        self.blocks.insert(self.cursor, BlockStruct(ListBlock, body=list(lists)))
        self.cursor += 1

    def paragraph(self, *paragraphs: str):
        self.blocks.insert(self.cursor, BlockStruct(ParagraphBlock, body=list(paragraphs)))
        self.cursor += 1

    def title(self, title: str, level: int = 1):
        for title_block in Block.__subclasses__():
            if title_block.__name__ == f'TitleBlock{level}':
                self.blocks.insert(self.cursor, BlockStruct(title_block, header=title))
                self.cursor += 1
                break

    def __find_title_path_range(self, *title_path):
        start = 0
        end = len(self.blocks) - 1 if self.blocks else 0
        for title in title_path:
            start, end = self.__find_title_index(title, start, end)
        return start, end

    def __find_title_index(self, title, start, end):
        title_index = None
        title_level = None
        for i, block in zip(itertools.count(start), self.blocks[start:end]):
            if block.header == title and block.block.__name__.startswith('TitleBlock'):
                title_index = i
                title_level = int(block.block.__name__[-1])
                continue
            if title_index and block.block.__name__.startswith('TitleBlock') and int(
                    block.block.__name__[-1]) <= title_level:
                title_end = i
                return title_index, title_end
        title_end = end
        return title_index, title_end

    def locate(self, *titles: str, head: bool = False, after=None, index: int = None):
        find_from = 0
        find_end = len(self.blocks)
        if titles:
            find_from, find_end = self.__find_title_path_range(*titles)
        if index is not None:
            self.cursor = index
        elif head:
            self.cursor = find_from + 1
        elif after:
            for i, b in zip(itertools.count(find_from), self.blocks[find_from:find_end]):
                if after(b):
                    self.cursor = i + 1
        else:
            self.cursor = find_end + 1

    def find(self, *title_path: str, block_filter=None):
        find_from = 0
        find_end = len(self.blocks)
        if title_path:
            find_from, find_end = self.__find_title_path_range(*title_path)
        if block_filter:
            for i, block in zip(itertools.count(find_from), self.blocks[find_from:find_end]):
                if block_filter(block):
                    return i, block
        return None, None

    def __parse_block(self, text):
        if text:
            lines_iter = MarkdownIterator(text)
            for line in lines_iter:
                block = parse_block(line, lines_iter)
                if not block.block == EmptyBlock:
                    self.blocks.append(block)
        self.cursor = len(self.blocks) - 1 if self.blocks else 0

    def __enter__(self):
        if self.text is not None:
            self.__parse_block(self.text)
            return self
        self.file = open(self.path, self.mode)
        if self.file and os.path.isfile(self.path):
            text = self.file.read()
            self.__parse_block(text)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file:
            self.file.write('\n\n'.join([i for i in [match_block_map[b.block].dumps(b.header, b.body) for b in self.blocks] if i]))
            self.file.close()

    def show_block(self):
        print('\n'.join([f'{i}\t{b}' for i, b in zip(itertools.count(1), self.blocks)]))

    def show_md(self):
        print('\n\n'.join([match_block_map[b.block].dumps(b.header, b.body) for b in self.blocks]))


def open_md(path: str = None, mode='r', text: str = None) -> MarkdownContext:
    return MarkdownContext(path=path, mode=mode, text=text)


if __name__ == '__main__':
    md = '''# 标题

这是一个示例Markdown文本。

## 列表

- 列表项1
- 列表项2
- 列表项3

## 表格

| 列1 | 列2 | 列3 |
|-----|-----|-----|
| 1   | 2   | 3   |
| 4   | 5   | 6   |

## 代码块

```python
print('Hello, World!')
```

# title2
'''
    with open_md(text='') as f:
        f.title("标题")
        f.paragraph("hello")
        f.title("列表", level=2)
        f.list('list1', 'list2', 'list3')
        f.title("table", level=2)
        f.table(['col1', 'col2', 'col3'], ['col4', 'col5', 'col6'])
        f.title("code", level=2)
        f.code('python', 'print(\'hello world\')')
        f.locate("标题")
        f.paragraph("append index")
        f.show_block()
