import sys
import pygame
import time
import json
from pygame.locals import *
from constants import *
from deck import *
from player import *
from result import *
from operator import itemgetter
from graphics import *


class ServerGame:
	def __init__(self, clientSockets, screen):
		self.clientSockets = clientSockets
		self.screen = screen

	# one match = several games, one game = 4 rounds
	def update_game(self, receivedBetValue):
		if receivedBetValue < 0:
			self.numberOfUnfoldedPlayers -= 1
			self.players[self.turn].do_fold()
			# self.players[self.turn].pot = 0
		else:

			amount = self.players[self.turn].bet(receivedBetValue)
			self.roundPot += amount
			if self.players[self.turn].currentRoundBet > self.currentRoundBet:
				self.currentRoundBet = self.players[self.turn].currentRoundBet
				self.lastRaisedPlayer = self.turn

	def init_round(self):
		for i in range(self.numberOfPlayers):
			self.players[i].currentRoundBet = 0

		if self.infoFlag == 0:
			self.currentRoundBet = self.bigBlind

			temp1 = (self.start + 1) % self.numberOfPlayers
			while self.players[temp1].isActive is False:
				temp1 = (temp1 + 1) % self.numberOfPlayers

			self.players[self.start].bet(self.smallBlind)
			self.players[temp1].bet(self.bigBlind)

			temp2 = (temp1 + 1) % self.numberOfPlayers
			while self.players[temp2].isActive is False:
				temp2 = (temp2 + 1) % self.numberOfPlayers
			self.turn = temp2

			self.roundPot = self.players[self.start].currentRoundBet + self.players[temp1].currentRoundBet
		else:
			self.currentRoundBet = 0
			self.roundPot = 0
			self.turn = self.start

		self.lastRaisedPlayer = self.turn

		self.toCallAmount = self.currentRoundBet - self.players[self.serverTurn].currentRoundBet

	def start_round(self):
		self.init_round()

		if self.numberOfUnfoldedPlayers <= 1:
			return

		while True:
			self.toCallAmount = self.currentRoundBet - self.players[self.serverTurn].currentRoundBet
			self.before_move(self.g, self.screen)
			if (not self.players[self.turn].fold) and self.players[self.turn].money != 0 and self.players[self.turn].isActive:
				self.broadcast()
				if self.turn == self.serverTurn:
					recievedBetValue = self.server_move(self.g, self.screen)
				else:
					self.client_move(self.g, self.screen)
					# Wait for client move
					recievedBetValue = int(self.clientSockets[self.turn].recv(1024))

				self.update_game(recievedBetValue)

			self.exTurn = self.turn
			self.exPot = self.pot
			self.turn = (self.turn + 1) % self.numberOfPlayers

			self.after_move(self.g, self.screen)

			if self.turn == self.lastRaisedPlayer or self.numberOfUnfoldedPlayers <= 1:
				break
		self.fin_round()

	def fin_round(self):
		self.pot += self.roundPot
		self.roundPot = 0
		self.numberOfUnfoldedPlayers = 0
		for i in range(self.numberOfPlayers):
			self.players[i].currentRoundBet = 0
			if not self.players[i].fold and self.players[i].money != 0:
				self.numberOfUnfoldedPlayers += 1

	def init_hand(self):
		self.deck = Deck()
		self.tableCards = []
		self.smallBlind = 10
		self.bigBlind = self.smallBlind * 2
		self.handWinners = []
		self.numberOfUnfoldedPlayers = self.numberOfActivePlayers
		self.pot = 0
		self.winCards = (self.deck.pop(), self.deck.pop())
		# Initializing cards
		self.cards = {0: []}

		i = 0
		for cSock in self.clientSockets:
			self.cards[cSock] = (self.deck.pop(), self.deck.pop())
			self.cards[i] = self.cards[cSock]
			i += 1
		# Server Cards
		self.cards[self.serverTurn] = (self.deck.pop(), self.deck.pop())

		self.myCards = self.cards[self.serverTurn]

		for i in range(self.numberOfPlayers):
			self.players[i].pot = 0
			self.players[i].fold = False

	def start_hand(self):
		self.init_hand()

		self.infoFlag = 0
		self.start_round()

		self.tableCards.append(self.deck.pop())
		self.tableCards.append(self.deck.pop())
		self.tableCards.append(self.deck.pop())
		self.infoFlag = 1
		self.start_round()

		self.tableCards.append(self.deck.pop())
		self.infoFlag = 2
		self.start_round()

		self.tableCards.append(self.deck.pop())
		self.infoFlag = 3
		self.start_round()

		self.infoFlag = 10
		print "Hand completed"
		self.fin_hand()

	def fin_hand(self):

		# Hand result
		self.hand_result()

		# Decrese numberOfActivePlayers and remove from activePlayers
		for i in self.activePlayers:
			if self.players[i].money == 0:
				self.players[i].isActive = False
				self.numberOfActivePlayers -= 1
				self.activePlayers.remove(i)
		# increment start
		self.start = (self.start + 1) % self.numberOfPlayers
		while self.players[self.start].isActive is False:
			self.start = (self.start + 1) % self.numberOfPlayers

		self.turn = -1
		self.broadcast()
		self.after_move(self.g, self.screen)

	def init_game(self):
		self.resultRating = 0

		self.init_gui()

		self.numberOfPlayers = len(self.clientSockets) + 1
		self.numberOfActivePlayers = self.numberOfPlayers
		self.gameWinner = -1
		self.serverTurn = self.numberOfPlayers - 1
		self.start = 0
		self.myTurn = self.serverTurn
		self.exTurn = -1

		# Initializing cards and player
		self.players = {0: []}
		for i in range(self.numberOfPlayers):
			self.players[i] = Player(i, "client " + str(i))
		self.players[self.serverTurn].name = "Server"

		# List of ids of active players
		self.activePlayers = range(self.numberOfActivePlayers)

	def start_game(self):
		self.init_game()

		# Multiple hands : game > hand > round
		while self.numberOfActivePlayers > 1:
			self.start_hand()

		self.fin_game()

	def fin_game(self):
		pass

	def broadcast(self):
		i = 0
		for cSock in self.clientSockets:
			maxPlayerMoney = 0
			for j in self.activePlayers:
				if not self.players[j].fold and j != i:
					maxPlayerMoney = max(maxPlayerMoney, self.players[j].money + self.players[j].currentRoundBet)

			maxBet = min(maxPlayerMoney - self.players[i].currentRoundBet, self.players[i].money)

			msgPlayerCards = json.dumps(self.cards[cSock])
			msgPlayers = json.dumps(self.players, default=lambda o: o.__dict__)
			msgTableCards = json.dumps(self.tableCards)

			toCallAmount = self.currentRoundBet - self.players[i].currentRoundBet
			things = (self.turn, self.numberOfPlayers, self.pot, toCallAmount, self.infoFlag, self.winCards, maxBet, self.resultRating)
			msgThings = json.dumps(things)
			msgWinners = json.dumps(self.handWinners)
			completeMessage = msgPlayerCards + "::" + str(i) + "::" + msgPlayers + "::" + msgTableCards + "::" + msgThings + "::" + msgWinners
			i += 1

			cSock.send(completeMessage)
			print "Size of message sent : " + str(sys.getsizeof(completeMessage)) + " B"

	def hand_result(self):
		obj = Result()
		handStrengths = []
		extraMoney = {0: []}
		moneyToGive = []
		for i in range(self.numberOfPlayers):
			moneyToGive.append(0.0)
		for i in self.activePlayers:
			extraMoney[i] = float(self.players[i].pot)
			if not self.players[i].fold:
				playerCards = self.tableCards[:]
				playerCards.append(self.cards[i][0])
				playerCards.append(self.cards[i][1])
				a, b = obj.hand_strength(playerCards)
				handStrengths.append((i, a, b, self.players[i].pot))

		handPot = sorted(handStrengths, key=itemgetter(3), reverse=True)
		handStrengths = sorted(handStrengths, key=itemgetter(1), reverse=True)

		length = len(handStrengths)
		for i in range(length - 1):
			if handStrengths[i][1] == handStrengths[i + 1][1]:
				comp = obj.hand_comparator(handStrengths[i][2], handStrengths[i + 1][2])
				if comp == 2:
					handStrengths[i], handStrengths[i + 1] = handStrengths[i + 1], handStrengths[i]

		# Remove all from handPot who will not get any money
		for i in range(length):
			temp = handStrengths[i]
			for j in range(length):
				if handStrengths[j][3] >= handStrengths[i][3]:
					if handStrengths[j][1] > handStrengths[i][1] or (handStrengths[j][1] == handStrengths[i][1] and obj.hand_comparator(handStrengths[j][2], handStrengths[i][2]) == 1):
						handPot.remove(temp)
						break

		handPot = sorted(handPot, key=itemgetter(3), reverse=True)
		length = len(handPot)

		print handPot
		print length
		print extraMoney

		self.handWinners = []
		for i in range(length):
			self.handWinners.append(handPot[i][0])

		extraMoneyLength = len(extraMoney)

		while self.pot != 0 and len(handPot) > 0:
			length = len(handPot)
			if length == 1:
				self.players[handPot[0][0]].money += self.pot
				break

			countEqual = 1
			for i in range(1, length):
				if handPot[i][1] == handPot[0][1] and obj.hand_comparator(handPot[i][2], handPot[0][2]) == 0:
					countEqual += 1
				else:
					break
			print countEqual
			while True:
				largestPot = handPot[0][3]
				lessPot = 0
				count = 1
				for i in range(1, length):
					if handPot[i][3] < largestPot:
						lessPot = handPot[i][3]
						break
					count += 1
				# diffPot = largestPot - lessPot
				exMon = 0
				for i in range(extraMoneyLength):
					exMon += extraMoney[i] - min(lessPot, extraMoney[i])
					extraMoney[i] = min(lessPot, extraMoney[i])
				tempd = int(count)

				for i in range(0, tempd):
					tmp = handPot[i][0]
					moneyToGive[tmp] = moneyToGive[tmp] + exMon / count
					hp = (handPot[i][0], handPot[i][1], handPot[i][2], lessPot)
					handPot[i] = hp
				self.pot -= exMon

				if count == countEqual:
					for i in range(tempd):
						del handPot[0]
					break

		for i in range(self.numberOfPlayers):
			self.players[i].money += moneyToGive[i]
			self.players[i].money = int(self.players[i].money)

		self.pot = 0

		self.winCards = self.cards[self.handWinners[0]]
		self.resultRating = handStrengths[0][1]


def unpause_clients(clientSockets):
	for obj in clientSockets:
		obj.send("begin")


def main(screen, clientSockets):
	unpause_clients(clientSockets)
	print "Inside serverGame file : Method main()"

	game = ServerGame(clientSockets, screen)
	game.start_game()

	time.sleep(5)
	pygame.quit()
	sys.exit()


if __name__ == '__main__':
	main()