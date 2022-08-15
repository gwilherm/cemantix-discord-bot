# Makefile

SHELL := /bin/bash

all: venv deps discord-token
	@echo "Done. You can run the bot with the following command:"
	@echo "./cemantixbot.sh" 

venv:
	python3 -m venv venv

deps:
	venv/bin/pip3 install -r requirements.txt

discord-token:
	@[ -f "token.sh" ]|| { \
		prompt="Please paste your discord bot token: "; \
		if command -v whiptail &> /dev/null; then \
			token=$$(whiptail --inputbox "$${prompt}" 10 77 --title "Token" 3>&1 1>&2 2>&3); \
		else \
			read -p "$${prompt}" token; \
		fi; \
		if [ -n "$${token}" ]; then \
			echo export CEMANTIX_BOT_TOKEN=\"$${token}\" > token.sh; \
		fi \
	}
