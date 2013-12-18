#!/usr/bin/env python
"""
    Copyright (C) 2013  Mattias Ugelvik <uglemat@gmail.com>

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

from __future__ import print_function

import pygame as pg
from pygame import Rect, Surface

from collections import namedtuple
import random
import glob
import re
import json
import string
import webbrowser
import math
import os

import kezmenu

from scores import load_score, write_score
from words import words

pg.init()

WIDTH = 1000
HEIGHT = 700

BACKSPACE = '\x08'

def get_font(height):
    return pg.font.Font(os.path.join(os.path.dirname(__file__),
                                     "resources/font/AnonymousPro-1.002.001/Anonymous Pro B.ttf"),
                        height)

def endswith_any(s, *suffixes):
    return any(s.endswith(suffix) for suffix in suffixes)

def renderpair(text, val, font, width, textcolor=pg.Color("darkblue"), background=False, bgcolor=(0,0,0,195)):
    text = font.render(text, True, textcolor)
    val = font.render(str(val), True, textcolor)

    surf = Surface((text.get_rect().width + width, text.get_rect().height),  pg.SRCALPHA, 32)
    if background:
        surf.fill(bgcolor)

    surf.blit(text, (3,0))
    surf.blit(val, val.get_rect(right=surf.get_rect().right-3))
    return surf

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


def transform_color(color, changes, max_=255, min_=0):
    """ Return an RGB triplet which has changed slightly from the color taken as input """
    assert max_ < 256 and min > 0 and max_ >= min_
    red, green, blue = color

    result = []
    for color in (red, green, blue):
        highest = min(color + changes, max_)
        lowest  = max(color - changes, min_)

        if lowest >= highest: 
            highest = lowest+1
        
        result.append(random.randrange(lowest, highest))

    return tuple(result)


class Background(object):
    def __init__(self, size):
        width, height = self.size = size

        self.surf = Surface(size)

        self.backgrounds = [   ]

        is_image = lambda fname: endswith_any(fname, '.jpg', '.png')
        files = glob.glob(os.path.join(os.path.dirname(__file__), "resources/backgrounds/*"))

        bg = namedtuple("background", "image info")
        for fname in filter(is_image, files):
            self.backgrounds.append(
                bg(image = stretch(pg.image.load(fname).convert(), self.size),
                   info  = json.load(open("{}.json".format(fname))))
                )

        random.shuffle(self.backgrounds)

        self.timer = 0
        self.frequency = 25 # new background ever N seconds
        self.current_bg = 0 # index of the current bg in self.backgrounds


        self.fadetime = .7
        self.fading = 0
        self.donefading = True

        self.set_background()


    def update(self, timepassed):
        old_timer, self.timer  = self.timer, (self.timer+timepassed) % self.frequency

        if self.fading < 0:
            self.donefading = True
            self.fading = 0
        elif self.fading:
            self.fading = self.fading-timepassed

        if old_timer > self.timer:
            old_bg, self.current_bg = self.current_bg, (self.current_bg+1) % len(self.backgrounds)
            if self.current_bg != old_bg:
                self.fading = self.fadetime

        if self.fading:
            self.set_background()
        elif self.donefading:
            self.donefading = False
            self.set_background()

    def get_current_bg(self):
        return self.backgrounds[self.current_bg]

    def set_background(self):
        if self.fading:
            old_bg = (self.current_bg-1) % len(self.backgrounds)
            new = self.get_current_bg().image
            old = self.backgrounds[old_bg].image.copy()
            old.set_alpha(self.fading*255/self.fadetime)


            self.blit(new)
            self.blit(old)
        else:
            self.blit(self.get_current_bg().image)

    def browse(self, direction):
        dirs = {'forward':1, 'backward':-1}
        self.current_bg = (self.current_bg+dirs[direction]) % len(self.backgrounds)
        self.set_background()
        self.timer = 0

    def blit(self, surf):
        self.surf.blit(surf, surf.get_rect(centerx=self.surf.get_rect().centerx,
                                           centery=self.surf.get_rect().centery))


class Game(object):
    def __init__(self, size, difficulty=0):
        pg.key.set_repeat(250, 30) 
        # ^ Because it's important to be able to hold down the backspace key for clearing the prompt

        self.difficulty = difficulty
        # difficulty will be a number signifying difficulty.
        # 0 is easy, 1 is medium, 3 is hard. I use this number various places to make it a little more difficult.

        self.width, self.height = self.size = size
        self.surf = Surface(size)

        self.prompt_font = get_font(40) # This font it also used for the dangling words, so the name is confusing
        self.prompt_font_height = self.prompt_font.size("Test")[1]
        self.prompt_content = ''

        self.borderwidth = 3 # Used by generate_info_surf and generate_prompt_surf
        self.bgcolor = (40, 40, 40)
        self.bordercolor = pg.Color("orange")
        self.textcolor = pg.Color("white")

        self.current_words = dict() # Dict that looks like this: {word: [x_position, time_word_has_existed, color]}.
        """ time_word_has_existed is used to calculate its y position and it's also put into math.cos and
        ''' added to the x position to make the word move gently from side to side.
        """

        self.score = 0
        self.level = 1
        self.max_health = 5
        self.health = self.max_health
        self.words_killed = 0

        self.info_surf_height = self.generate_info_surf().get_rect().height
        self.prompt_surf_height = self.generate_prompt_surf().get_rect().height

        self.background_height = (HEIGHT - 
                                  self.info_surf_height -
                                  self.prompt_surf_height)
        self.background = Background((WIDTH, self.background_height))

        self.allowed_chars = string.ascii_letters + BACKSPACE

        self.compile_words(self.level)

        self.photo_info_rect = renderpair("Photo:",
                                          """Blabla whatever, this invocation of renderpair is only made to
                                             measure the size of the resulting surface""",
                                          get_font(18),
                                          250).get_rect(right=self.width-20,
                                                        bottom=self.height-self.prompt_surf_height-20)

    def main(self, screen):
        clock = pg.time.Clock()


        word_frequency = 2.5  # new word every N second
        word_speed = 30 + (self.difficulty*3) # pixels downwards per second
        word_timer = 0

        paused = False

        while True:
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    exit()
                elif event.type == pg.KEYDOWN and event.unicode in self.allowed_chars and event.unicode != '':
                    if event.unicode == BACKSPACE:
                        self.prompt_content = self.prompt_content[:-1]
                    elif self.prompt_font.size(self.prompt_content + event.unicode)[0] < WIDTH:
                        # ^ Ensuring the content of the prompt stays approximately within the boundraries of the screen
                        self.prompt_content += event.unicode
                elif event.type == pg.MOUSEBUTTONDOWN and self.photo_info_rect.collidepoint(event.pos):
                    source = self.background.get_current_bg().info['source']
                    print("Attempting to open {url} in webbrowser.".format(url=source))
                    webbrowser.open(source)
                elif event.type == pg.KEYDOWN and event.key in (pg.K_RIGHT, pg.K_LEFT):
                    self.background.browse({pg.K_RIGHT: 'forward', pg.K_LEFT: 'backward'}[event.key])
                elif event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                    write_score(self.score)
                    return
                elif event.type == pg.KEYDOWN and event.key == pg.K_RETURN:
                    paused = not paused
                    if paused:
                        screen.fill((0,0,0))
                        screen.blit(get_font(23).render("Pause (press enter to return (pardon the pun))", 
                                                        True, (80,80,80)),
                                    (40,40))
                        pg.display.flip()

            if paused:
                clock.tick(35)
                continue

            timepassed = clock.tick(35) / 1000.


            old_wt, word_timer = word_timer, (word_timer+timepassed) % word_frequency
            if old_wt > word_timer:
                self.add_word()


            old_level, self.level = self.level, 1 + self.words_killed/10
            if self.level > old_level:
                self.compile_words(self.level)

                word_frequency *= 0.99
                """ Each level, word_frequency becomes 99 percent of itself. If word_frequency starts out at 2.5, then
                ''' it will become around 2.065 on level 20:
                '''     for level in range(1, 21): print("Level {:<3}= {:.3f} Seconds".format(level, 2.5 * (0.99 ** (level - 1))))
                """

                print("Word frequency:", word_frequency)


            if self.health <= 0:
                write_score(self.score)
                return

            if len(self.current_words) < 1:
                self.add_word()
                word_timer = 0

            for word in self.current_words:
                self.current_words[word][1] += timepassed
                self.current_words[word][2] = transform_color(self.current_words[word][2], 29,
                                                              max_=240,
                                                              min_=100)

            self.background.update(timepassed)
            self.surf.blit(self.background.surf,
                           self.background.surf.get_rect(centerx=screen.get_rect().centerx,
                                                         centery=self.background_height/2 + self.info_surf_height))


            for word, meta in self.current_words.items():
                """ math.cos is used to make the words move softly and delicately like
                ''' a leaf traveling in the wind an autum..... no. I don't feel very well, I feel like..
                ''' like I'm not me anymore, HELP ME PLEASE, IF YOU'RE OUT THERE
                '''
                ''' The multipliers on the result are pretty arbitrary, just to make the words move at the
                ''' right speed.
                """
                y = (meta[1]*word_speed) + abs(math.cos(meta[1]*3)*10)
                if y > HEIGHT:
                    del self.current_words[word]
                    self.health -= 1
                elif word == self.prompt_content.lower():
                    del self.current_words[word]
                    self.score += len(word)
                    self.words_killed += 1
                    self.prompt_content = ''
                else:
                    self.surf.blit(self.create_word_surf(word, meta[2]), (meta[0] + math.cos(meta[1]*3)*8, y))

            self.surf.blit(renderpair("Photo:",
                                      self.background.get_current_bg().info["photo"],
                                      get_font(18),
                                      250,
                                      textcolor=(0,0,0),
                                      background=True,
                                      bgcolor=((25,155,215,108) if self.photo_info_rect.collidepoint(pg.mouse.get_pos())
                                               else (255,255,215,108))),
                           self.photo_info_rect)

            self.surf.blit(self.generate_info_surf(), (0,0))
            prompt_surf = self.generate_prompt_surf()
            self.surf.blit(prompt_surf, (0, HEIGHT-prompt_surf.get_rect().height))

            screen.blit(self.surf, (0, 0))
            pg.display.flip()


    def create_word_surf(self, word, color):
        w, h = self.prompt_font.size(word)
        w += 8
        size = (w, h)

        being_written = len(self.prompt_content) > 0 and word.startswith(self.prompt_content.lower())
        start = self.prompt_content.lower() if being_written else ''
        end = word[len(self.prompt_content):] if being_written else word

        start_surf = self.prompt_font.render(start, True, pg.Color("black"))
        end_surf = self.prompt_font.render(end, True, color)

        together = Surface(size, pg.SRCALPHA, 32)

        together.fill((50,50,50, 190))

        together.blit(start_surf, (4, 0))
        together.blit(end_surf, end_surf.get_rect(right=w-4))

        return together

    def add_word(self):
        found_word = False
        while not found_word and len(self.possible_first_characters) > len(self.current_words):
            selected = random.choice(self.words)
            if all(not w.startswith(selected[0]) for w in self.current_words.keys()):
                found_word = True
                self.current_words[selected] = [random.randrange(0, WIDTH-self.prompt_font.size(selected)[0]), 0,
                                                (150,150,150)]

    def compile_words(self, level):
        w = set()
        for i in range(2, level+3 + self.difficulty):
            w = w.union(words.get(i, {}))
        self.words = list(w)
        self.possible_first_characters = {word[0] for word in self.words}

    def generate_info_surf(self, font=get_font(25)):

        infos = map(lambda i: renderpair(i[0], i[1], font, 100, textcolor=i[2]),
                    [ ("Score",  str(self.score),  self.textcolor),
                      ("Health", str(self.health), (255, 255/self.max_health*self.health, 255/self.max_health*self.health)),
                      ("Words",  str(self.words_killed), self.textcolor),
                      ("Level",  str(self.level),  self.textcolor)
                      ]) # The color of the health will get increasingly red as the health approaches zero

        height = infos[0].get_rect().height + self.borderwidth*2 + 10
        surf = Surface((WIDTH, height))

        surf.fill(self.bgcolor)

        gen_borderx = lambda n: (WIDTH/len(infos)) * (1+n)
        gen_centerx = lambda n: gen_borderx(n) - (WIDTH/len(infos)/2)


        for index, infosurf in enumerate(infos):
            surf.blit(infosurf, infosurf.get_rect(centerx=gen_centerx(index), centery=height/2))
            
            if index+1 < len(infos):
                borderx = gen_borderx(index)
                pg.draw.line(surf, self.bordercolor, (borderx, 0), (borderx, height), self.borderwidth)

        pg.draw.rect(surf, self.bordercolor, surf.get_rect(), self.borderwidth*2)
        # ^ borderwidth*2 since it seems like 1/2 of the rect is drawn outside of the surface
        return surf

    def generate_prompt_surf(self):
        surf = Surface((WIDTH, self.prompt_font_height+self.borderwidth*2))
        surf.fill(self.bgcolor)
        color = self.textcolor if any([w.startswith(self.prompt_content.lower()) 
                                       for w in self.current_words]) else pg.Color("red")
        rendered = self.prompt_font.render(self.prompt_content.upper(), True, color)
        surf.blit(rendered, rendered.get_rect(left=self.borderwidth+4, centery=surf.get_rect().height/2))
        pg.draw.rect(surf, self.bordercolor, surf.get_rect(), self.borderwidth*2)
        return surf



class Menu(object):
    running = True
    def main(self, screen):
        clock = pg.time.Clock()
        menu = kezmenu.KezMenu(
            ['Play Game (easy)',   lambda: Game(screen.get_size(), difficulty=0).main(screen)],
            ['Play Game (medium)', lambda: Game(screen.get_size(), difficulty=1).main(screen)],
            ['Play Game (hard)',   lambda: Game(screen.get_size(), difficulty=3).main(screen)],
            ['Quit', lambda: setattr(self, 'running', False)],
        )
        menu.position = (50, 50)
        menu.enableEffect('enlarge-font-on-focus', font=None, size=60, enlarge_factor=1.2, enlarge_time=0.3)
        menu.color = (150,150,150)
        menu.focus_color = (40, 40, 240)

        highscoresurf = self.construct_highscoresurf()
        background = self.contruct_menu_background(screen.get_size())

        while self.running:
            events = pg.event.get()
            timepassed = clock.tick(30) / 1000.

            if timepassed > 1:
                highscoresurf = self.construct_highscoresurf()

            for event in events:
                if event.type == pg.QUIT:
                    exit()

            menu.update(events, timepassed)

            screen.blit(background, (0,0))
            screen.blit(highscoresurf, highscoresurf.get_rect(right=WIDTH-50, bottom=HEIGHT-50))
            menu.draw(screen)
            pg.display.flip()

    def contruct_menu_background(self, size):
        changes = 5
        
        bg = Surface(size) # Surface with horizontal lines
        bg2 = Surface(size, pg.SRCALPHA, 32) # Surfave with vertical lines


        red, green, blue = (100, 100, 100)
        for y in range(HEIGHT):
            red, green, blue = transform_color((red, green, blue), changes, max_=200, min_=30)
            pg.draw.line(bg, (red, green, blue), (0, y), (WIDTH-1, y))

        red, green, blue = (10, 10, 10)
        for x in range(0, WIDTH):
            red, green, blue = transform_color((red, green, blue), changes, max_=55)
            pg.draw.line(bg2, pg.Color(red, green, blue, 100), (x, 0), (x, HEIGHT))


        bg2.set_alpha(255/2)  # 50% vertical lines, 50% horizontal lines
        bg.blit(bg2, (0,0))

        return bg

    def construct_highscoresurf(self):
        font = pg.font.Font(None, 50)
        highscore = load_score()
        text = "Highscore: {}".format(highscore)
        return font.render(text, True, (150,150,150))

if __name__ == '__main__':
    screen = pg.display.set_mode((WIDTH, HEIGHT), pg.DOUBLEBUF)
    screen.set_alpha(None)
    pg.display.set_caption("MaType")
    Menu().main(screen)
