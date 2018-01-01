import sys
import random
from string import printable
from collections import defaultdict

dictfile = sys.argv[1]


words = defaultdict(set)


with open(dictfile) as file:
    wordlist = [w for w in file.read().split()]

random.shuffle(wordlist)
wordlist = filter(lambda w: all(c in printable for c in w), wordlist)
wordlist = wordlist[:1300]

for word in wordlist:
    words[len(word)].add(word)

with open("words.py", "w") as file:
    file.write("words = {}".format(repr(dict(words))))
