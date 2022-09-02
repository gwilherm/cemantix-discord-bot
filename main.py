#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import json
import logging
import asyncio
import discord
import requests
from discord.ext import commands
from collections import OrderedDict
from collections import namedtuple
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from Game import Game

MAX_HISTORY = 20

Result  = namedtuple('Result', ['word', 'try_number', 'temperature', 'points'])

# Change only the no_category default string
help_command = commands.DefaultHelpCommand(
    no_category='Commands'
)

bot = commands.Bot(
    command_prefix='!',
    description='CemantixBot',
    help_command=help_command
)

async def game_over():
    global bot
    global games
    global settings
    global word_to_guess
    async with mutex:
        yesterday_word=[]
        for serv in settings['servers']:
            resp = requests.get(serv['host'] + '/history').json()
            yesterday_word.append(resp[1][2])

        coro = []

        for chan,game in games.items():
            if not game.guessed:
                try:
                    coro.append(bot.get_channel(chan).send(f'Partie terminée ! Le mot à deviner était `{yesterday_word[game.server]}`'))
                except Exception as e:
                    logger.error(e)
        coro.append(bot.change_presence(activity=None))

        games = dict()

        await asyncio.gather(*coro)


def format_result(result: Result):
    if result.try_number:
        result_str = f'n°{result.try_number:>4}'
    else:
        result_str = '      '
    result_str += f'\t{result.word:>20}\t{result.temperature:>6.2f}°C'
    if result.points:
        result_str += f'\t{result.points}‰'
    result_str += '\n'
    return result_str


def get_emoji(temp, points):
    if temp < 0:
        return '\N{Ice Cube}'
    else:
        if not points:
            return '\N{Freezing Face}'
        elif points <= 900:
            return '\N{Smiling Face with Sunglasses}'
        elif points <= 989:
            return '\N{Overheated Face}'
        elif points <= 998:
            return '\N{Fire}'
        elif points == 999:
            return '\N{Face Screaming In Fear}'
        elif points >= 1000:
            return '\N{Face with Party Horn and Party Hat}'


def nearby(game, word):
    global settings
    game_guesses = dict((g.word, g.try_number) for g in game.guesses.values())
    serv_num = game.server
    host = settings['servers'][serv_num]['host']
    resp = requests.post(host + '/nearby', data={"word": word}).json()
    nearby_str = '```\n'
    for w in list(reversed(resp[:MAX_HISTORY])):
        try_number = game_guesses.get(w[0])
        nearby_str += format_result(Result(w[0], try_number, float(w[2]), w[1]))
    nearby_str += '\n```'
    return nearby_str


def history(game):
    history_str = '```\n'
    od = OrderedDict(sorted(game.guesses.items()))
    for k, v in list(od.items())[-MAX_HISTORY:]:
        history_str += format_result(Result(*v))
    history_str += '\n```'
    return history_str


@bot.command(help='Try your word', aliases=['g'])
async def guess(context, *args):
    global games
    global settings
    async with mutex:
        if len(args) > 0:
            proposition = args[0].lower()

            if context.channel.id not in games:
                games[context.channel.id] = Game(0)

            game = games[context.channel.id]

            try:
                host = settings['servers'][game.server]['host']
                resp = requests.post(host + '/score', data={"word": proposition}).json()
                
                if 'error' not in resp:
                    score=resp.get('score')
                    percentile=resp.get('percentile')

                    win = (score == 1.0)

                    temperature = score * 100
                    if proposition not in list(map(lambda x: x.word, game.guesses.values())):
                        try_number = len(game.guesses) + 1
                        result = Result(proposition, try_number, temperature, percentile)
                        game.guesses[temperature] = result
                        if not win:
                            await context.send(history(game))
                    else:
                        if not win:
                            await context.send(f'Le mot `{proposition}` a déjà été proposé.')
                        else:
                            await context.send(f'Trop tard, le mot a déjà été trouvé par {game.guessed.name} !')
                        result = game.guesses[temperature]

                    if win and not game.guessed:
                            await context.send(f'Bien joué <@{context.author.id}> ! Le mot était `{proposition}`')
                            game.guessed = context.author
                            await context.send(nearby(game, proposition))

                    result_str = '```\n' + format_result(result) + '\n```'
                    result_msg = await context.send(result_str)

                    await result_msg.add_reaction(get_emoji(temperature, percentile))
                else:
                    await context.send(re.sub('<.{0,1}i>', '`', resp['error']))
            except Exception as e:
                await context.send(f'Désolé, une erreur est survenue')
                logger.error(e)


@bot.command(help='Switch server', aliases=['s'])
async def server(context, *args):
    global games
    global settings
    async with mutex:
        chan = context.channel.id
        if len(args) > 0 and int(args[0]) > 0 and int(args[0]) <= len(settings['servers']): 
            serv_num = int(args[0]) - 1
            serv_name = settings['servers'][serv_num]['name']
            await context.send(f'Connexion au serveur `{serv_name}`')

            games[chan] = Game(serv_num)
        else:
            server_list_str = '```\n'
            for serv_num,serv in enumerate(settings['servers']):
                serv_name = serv['name']
                server_list_str += f'n°{serv_num+1}\t{serv_name}'
                if chan in games and games[chan].server == serv_num:
                    server_list_str += ' (Courant)'
                server_list_str += '\n'
            server_list_str += '```'

            await context.send(server_list_str)


@bot.command(help='Server stats')
async def stats(context):
    global games
    chan = context.channel.id

    serv_num = games[chan].server if chan in games else 0

    try:
        host = settings['servers'][serv_num]['host']
        resp = requests.get(host + '/stats').json()
        day_num = resp['num']
        solvers = resp['solvers']
        await context.send(f'Jour {day_num}: Mot trouvé par {solvers} personnes.')
    except Exception as e:
        await context.send(f'Désolé, une erreur est survenue')
        logger.error(e)


@bot.event
async def on_message_edit(before, after):
    await bot.process_commands(after)


if __name__ == '__main__':
    # create logger
    logger = logging.getLogger('CemantixBot')
    logger.setLevel(logging.DEBUG)

    # create console handler and set level to debug
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    # create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # add formatter to ch
    ch.setFormatter(formatter)

    # add ch to logger
    logger.addHandler(ch)

    with open('settings.json', 'r') as f:
        settings = json.load(f)

    # initialize global
    games = dict()

    # multithreading
    mutex = asyncio.Lock()

    scheduler = AsyncIOScheduler(timezone='Europe/Paris')
    scheduler.add_job(game_over, 'cron', hour=0, minute=0, second=1)
    scheduler.start()

    bot.run(os.environ['CEMANTIX_BOT_TOKEN'])
