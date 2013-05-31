import pygame as pg
from pygame import Rect, Surface
import random
import glob
import re
import json
import string
from collections import namedtuple

import kezmenu

from scores import load_score, write_score
from words import words

WIDTH = 800
HEIGHT = 600

def endswith_any(s, *suffixes):
    return any(s.endswith(suffix) for suffix in suffixes)

def stretch(surf, size):
    width, height = size

    imgw, imgh = surf.get_rect().size

    xfactor = float(width) / imgw
    surf = pg.transform.smoothscale(surf, (int(imgw * xfactor), int(imgh * xfactor)))

    new_imgw, new_imgh = surf.get_rect().size

    if new_imgh < height:
        yfactor = float(height) / new_imgh
        surf = pg.transform.smoothscale(surf, (int(new_imgw * yfactor), int(new_imgh * yfactor)))
        
    return surf

class Background(object):
    def __init__(self, size):
        width, height = self.size = size

        self.surf = Surface(size)

        self.backgrounds = [   ]

        is_image = lambda fname: endswith_any(fname, '.jpg', '.png')
        files = glob.glob("images/*")

        bg = namedtuple("background", "image info")
        for fname in filter(is_image, files):
            image = pg.image.load(fname)
            image_info = json.load(open("{}.json".format(fname)))
            self.backgrounds.append(bg(image=image, info=image_info))

        random.shuffle(self.backgrounds)

        self.timer = 0
        self.frequency = 30 # new background ever N seconds
        self.current_bg = 0

        self.set_background()

    def update(self, timepassed):
        old_timer, self.timer  = self.timer, (self.timer+timepassed) % self.frequency

        if old_timer > self.timer:
            self.current_bg = (self.current_bg+1) % len(self.backgrounds)
            self.set_background()

    def set_background(self):
        self.surf = stretch(self.backgrounds[self.current_bg].image, self.size)



class Game(object):
    def __init__(self, size):
        pg.key.set_repeat(250, 30)

        self.width, self.height = self.size = size
        self.surf = Surface(size)


        self.prompt_height = 40
        self.prompt_font = pg.font.Font(None, self.prompt_height)
        self.prompt_content = ''

        self.current_words = dict() # Dict that looks like this: {word: [x_position, time_word_has_existed]}.

        self.score = 0
        self.level = 1
        self.health = 100

        self.background = Background((WIDTH, HEIGHT-self.prompt_height))

        self.allowed_chars = string.ascii_letters + '\x08'

        self.compile_words(self.level)

    def main(self, screen):
        clock = pg.time.Clock()


        word_frequency = 2  # new word every 2nd second
        word_speed = 30 # pixels downwards per second
        word_timer = 0

        while 1:
            timepassed = clock.tick(45) / 1000.

            old_wt, word_timer = word_timer, (word_timer+timepassed) % word_frequency

            if old_wt > word_timer:
                self.add_word()

                
            for word in self.current_words:
                self.current_words[word][1] += timepassed


            for event in pg.event.get():
                if event.type == pg.QUIT:
                    exit()
                elif event.type == pg.KEYDOWN and event.unicode in self.allowed_chars: 
                    if event.unicode == '\x08': # backspace
                        self.prompt_content = self.prompt_content[:-1]
                    elif self.prompt_font.size(self.prompt_content + event.unicode)[0] < WIDTH:
                        self.prompt_content += event.unicode

            
            self.surf.blit(self.background.surf, self.background.surf.get_rect(centerx=screen.get_rect().centerx,
                                                                               centery=screen.get_rect().centery))


            for word, meta in self.current_words.items():
                y = meta[1]*word_speed
                if y > HEIGHT:
                    del self.current_words[word]
                    self.health -= len(word)
                elif word == self.prompt_content.lower():
                    del self.current_words[word]
                    self.score += len(word)
                    self.prompt_content = ''
                else:
                    self.surf.blit(self.create_word_surf(word), (meta[0], y))

            self.surf.blit(self.generate_prompt_surf(), (0, HEIGHT-self.prompt_height))

            screen.blit(self.surf, (0, 0))
            pg.display.flip()


    def create_word_surf(self, word):
        w, h = size = self.prompt_font.size(word)

        being_written = word.startswith(self.prompt_content.lower())
        start = self.prompt_content.lower() if being_written else ''
        end = word[len(self.prompt_content):] if being_written else word

        start_surf = self.prompt_font.render(start, True, pg.Color("green"))
        end_surf = self.prompt_font.render(end, True, pg.Color("white"))

        together = Surface(size, pg.SRCALPHA, 32)

        together.blit(start_surf, (0, 0))
        together.blit(end_surf, end_surf.get_rect(right=w))

        return together

    def add_word(self):
        found_word = False
        while not found_word and len(self.possible_first_characters) > len(self.current_words):
            selected = random.choice(self.words)
            if all(not w.startswith(selected[0]) for w in self.current_words.keys()):
                found_word = True
                self.current_words[selected] = [random.randrange(0, WIDTH-self.prompt_font.size(selected)[0]), 0]

    def compile_words(self, level):
        w = set()
        for i in range(2, level+4):
            w = w.union(words.get(i, {}))
        self.words = list(w)
        self.possible_first_characters = {word[0] for word in self.words}

    def generate_prompt_surf(self):
        surf = Surface((WIDTH, self.prompt_height))
        surf.fill((225,225,225))
        color = pg.Color("black") if any([w.startswith(self.prompt_content.lower()) for w in self.current_words]) else pg.Color("red")
        rendered = self.prompt_font.render(self.prompt_content, True, color)
        surf.blit(rendered, rendered.get_rect(left=10, centery=self.prompt_height/2))
        return surf



class Menu(object):
    running = True
    def main(self, screen):
        clock = pg.time.Clock()
        menu = kezmenu.KezMenu(
            ['Play!', lambda: Game(screen.get_size()).main(screen)],
            ['Quit', lambda: setattr(self, 'running', False)],
        )
        menu.position = (50, 50)
        menu.enableEffect('enlarge-font-on-focus', font=None, size=60, enlarge_factor=1.2, enlarge_time=0.3)
        menu.color = (255,255,255)
        menu.focus_color = (40, 200, 40)

        highscoresurf = self.construct_highscoresurf()

        while self.running:
            events = pg.event.get()
            timepassed = clock.tick(30) / 1000.

            for event in events:
                if event.type == pg.QUIT:
                    exit()

            menu.update(events, timepassed)

            screen.fill((30, 30, 90))
            screen.blit(highscoresurf, highscoresurf.get_rect(right=WIDTH-50, bottom=HEIGHT-50))
            menu.draw(screen)
            pg.display.flip()

    def construct_highscoresurf(self):
        font = pg.font.Font(None, 50)
        highscore = load_score()
        text = "Highscore: {}".format(highscore)
        return font.render(text, True, (255,255,255))

if __name__ == '__main__':
    pg.init()
    screen = pg.display.set_mode((WIDTH, HEIGHT))
    pg.display.set_caption("MaType")
    Menu().main(screen)
