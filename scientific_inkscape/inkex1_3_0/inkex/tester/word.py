# coding=utf-8
#
# Unknown author
#
"""
Generate words for testing.
"""

import string
import random


def word_generator(text_length):
    """
    Generate a word of text_length size
    """
    word = ""

    for _ in range(0, text_length):
        word += random.choice(
            string.ascii_lowercase
            + string.ascii_uppercase
            + string.digits
            + string.punctuation
        )

    return word


def sentencecase(word):
    """Make a word standace case"""
    word_new = ""
    lower_letters = list(string.ascii_lowercase)
    first = True
    for letter in word:
        if letter in lower_letters and first is True:
            word_new += letter.upper()
            first = False
        else:
            word_new += letter

    return word_new
