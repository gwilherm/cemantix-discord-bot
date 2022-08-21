#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import logging
import asyncio
import discord
import requests
from discord.ext import commands
from collections import OrderedDict
from collections import namedtuple
from apscheduler.schedulers.asyncio import AsyncIOScheduler

WORD_FILE = 'word.txt'
MAX_HISTORY = 20

Result = namedtuple('Result', ['word', 'try_number', 'temperature', 'points'])

SERVER_URL = 'https://cemantix.herokuapp.com'

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
    global guesses
    global guessed
    global word_to_guess
    async with mutex:
        resp = requests.get(SERVER_URL + '/history').json()
        yesterday_word = resp[1][2]

        coro = []
        for chan in guesses.keys():
            if chan not in guessed.keys():
                try:
                    coro.append(bot.get_channel(chan).send(f'Partie terminée ! Le mot à deviner était `{yesterday_word}`'))
                except Exception as e:
                    logger.error(e)
        coro.append(bot.change_presence(activity=None))

        guesses = dict()
        guessed = dict()

        await asyncio.gather(*coro)


def format_result(result: Result):
    result_str = f'n°{result.try_number:>4}\t{result.word:>20}\t{result.temperature:>6.2f}°C'
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


@bot.command(help='Try your word', aliases=['g'])
async def guess(context, *args):
    async with mutex:
        if len(args) > 0:
            proposition = args[0].lower()

            if context.channel.id not in guesses:
                guesses[context.channel.id] = dict()

            try:
                resp = requests.post(SERVER_URL + '/score', data={"word": proposition}).json()
                
                if 'error' not in resp:
                    solvers=resp.get('solvers')
                    score=resp.get('score')
                    percentile=resp.get('percentile')

                    if score == 1.0:
                        if context.channel.id not in guessed:
                            await context.send(f'Bien joué <@{context.author.id}> ! Le mot était `{proposition}`')
                            guessed[context.channel.id] = context.author                            
                        else:
                            await context.send(f'Trop tard, le mot a déjà été trouvé par {guessed[context.channel.id].name} !')

                    temperature = score * 100
                    if proposition not in list(map(lambda x: x.word, guesses[context.channel.id].values())):

                        try_number = len(guesses[context.channel.id]) + 1
                        result = Result(proposition, try_number, temperature, percentile)
                        guesses[context.channel.id][temperature] = result

                        history_str = '```\n'
                        od = OrderedDict(sorted(guesses[context.channel.id].items()))
                        for k, v in list(od.items())[-MAX_HISTORY:]:
                            history_str += format_result(Result(*v))
                        history_str += '\n```'
                        await context.send(history_str)
                    else:
                        await context.send(f'Le mot `{proposition}` a déjà été proposé.')
                        result = guesses[context.channel.id][temperature]

                    result_str = '```\n' + format_result(result) + '\n```'
                    result_msg = await context.send(result_str)

                    await result_msg.add_reaction(get_emoji(temperature, percentile))

                    await bot.change_presence(activity=discord.Activity(name=f'{solvers} gagnants aujourd\'hui.',
                                                                                type=discord.ActivityType.watching))
                else:
                    await context.send(re.sub('<.{0,1}i>', '`', resp['error']))
            except Exception as e:
                await context.send(f'Désolé, une erreur est survenue')
                logger.error(e)


@bot.event
async def on_message_edit(before, after):
    await bot.process_commands(after)


@bot.event
async def on_ready():
    await bot.change_presence(activity=None)

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

    # initialize global
    guesses = dict()
    guessed = dict()

    # multithreading
    mutex = asyncio.Lock()

    scheduler = AsyncIOScheduler(timezone='Europe/Paris')
    scheduler.add_job(game_over, 'cron', hour=0, minute=0, second=1)
    scheduler.start()

    bot.run(os.environ['CEMANTIX_BOT_TOKEN'])
