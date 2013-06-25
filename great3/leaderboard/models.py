from django.db import models, transaction
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from collections import defaultdict
import datetime
import os
import hashlib
import random
import pytz


# Create your models here.
SUBMISSION_SAVE_PATH=os.path.join(os.path.split(__file__)[0], '..','..','results')
PLACEHOLDER_SCORE = -1.0
PLACEHOLDER_RANK = 1000
MAXIMUM_ENTRIES_PER_DAY = 3
MAX_BOARDS_FOR_SCORING = 5
EXPERIMENT_CHOICES = [
	('Control','Control'),
	('Realistic Galaxy','Realistic Galaxy'),
	('Realistic PSF', 'Realistic PSF'),
	('Multi-epoch', 'Multi-epoch'),
	('Everything', 'Everything')
	]

class UserProfile(models.Model):
    user = models.OneToOneField(User)
    teams = models.ManyToManyField('Team', related_name='users', null=True, blank=True)
    def __unicode__(self):
    	return self.user.username


def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

post_save.connect(create_user_profile, sender=User)


class Team(models.Model):
	name = models.CharField(max_length=128, unique=True)
	notes = models.CharField(max_length=512)
	score = models.IntegerField(default=0)
	rank = models.IntegerField(default=PLACEHOLDER_RANK)

	def __unicode__(self):
		return self.name

	def calculate_score(self, tiebreak=False):
		scores = [entry.get_points() for entry in self.entry_set.all()]
		if tiebreak:
			new_score = sum(scores)
		else:
			scores = sorted(scores)[::-1]
			new_score = sum(scores[:MAX_BOARDS_FOR_SCORING])
		self.score = new_score
		self.save()
		return new_score

	def top_entries_by_rank(self, n=MAX_BOARDS_FOR_SCORING):
		return self.entry_set.order_by('rank','date')[:n]


	@classmethod
	@transaction.commit_manually()
	def update_ranks(cls):
		teams = cls.objects.order_by('-score')
		for rank,team in enumerate(teams):
			team.rank = rank+1
			team.save()
		transaction.commit()

	def number_entries(self):
		return len(self.entry_set.all())

	def rank_text(self):
		if self.rank==PLACEHOLDER_RANK:
			return "-"
		else:
			return str(self.rank)

	@classmethod
	def update_scores_and_ranks(cls):
		for team in cls.objects.all():
			team.calculate_score()
		cls.update_ranks()

	@classmethod
	def winning_teams(cls):
		teams = cls.objects.order_by('-score')
		if len(teams)==0:
			return [], PLACEHOLDER_SCORE
		top_team = teams[0]
		winners = [top_team]
		best_score = top_team.score
		for team in teams[1:]:
			if team.score==best_score:
				winners.append(team)
			else:
				break
		if len(winners)>1:
			scores = [(winner.calculate_score(tiebreak=True), winner) for winner in winners]
			scores.sort()  #python trick.  sorts by the first element of the tuple
			best_tiebreak_score = scores[0][0]
			winners = [w[1] for w in scores if w[0]==best_tiebreak_score]
			#what if there is still a tie? At the moment we neglect this

		return winners, best_score


def score_for_rank(rank):
	""" The score that a team gets if their top-ranked
		entry into a board is at the given rank.
	"""
	if   rank==1: return 16
	elif rank==2: return 8
	elif rank==3: return 4
	elif rank==4: return 2
	elif rank==5: return 1
	else: return 0



class Board(models.Model):
	name = models.CharField(max_length=128, unique=True)
	experiment = models.CharField(max_length=20, choices=EXPERIMENT_CHOICES)
	notes = models.CharField(max_length=512)
	space = models.BooleanField()
	varying = models.BooleanField()

	@transaction.commit_manually()
	def assign_ranks(self):
		entries = self.entry_set.order_by('-score', 'date')
		ranked_teams = []
		rank=1
		for entry in entries:
			if entry.team in ranked_teams:
				entry.rank=PLACEHOLDER_RANK
			else:
				ranked_teams.append(entry.team)
				entry.rank = rank
				rank += 1
			entry.save()
		transaction.commit()

	@classmethod
	def assign_all_ranks(cls):
		for board in cls.objects.all():
			board.assign_ranks()

	def number_entries(self):
		return len(self.entry_set.all())

	def __unicode__(self):
		return self.name

	def get_entry_at_rank(self, rank):
		try:
			return self.entry_set.filter(rank=rank).get()
		except Entry.DoesNotExist:
			return None


	def winner(self):
		return self.get_entry_at_rank(1)


class Entry(models.Model):
	team = models.ForeignKey('Team')
	name = models.CharField(max_length=128, unique=True)
	notes = models.CharField(max_length=512)
	user = models.ForeignKey(User)
	board = models.ForeignKey('Board')
	score = models.FloatField(default=PLACEHOLDER_SCORE)
	date = models.DateTimeField(auto_now_add=True)
	rank = models.IntegerField(default=PLACEHOLDER_RANK)

	def __unicode__(self):
		return self.name

	def rank_text(self):
		r = self.rank
		if r==PLACEHOLDER_RANK:
			return ""
		return str(r)

	def score_text(self):
		if self.score == PLACEHOLDER_SCORE:
			return "...Calculating..."
		else:
			return "%.1f" % self.score

	def get_points(self):
		return score_for_rank(self.rank)

	def points_text(self):
		p = self.get_points()
		if p==0:
			return ""
		top_entries = self.team.top_entries_by_rank()
		print top_entries
		in_my_top = self in top_entries
		if in_my_top:
			return str(p)
		else:
			return str(p) + " [X]"

	def get_filename(self):
		return os.path.join(SUBMISSION_SAVE_PATH, str(self.id)) + '.g3_result'


def recompute_scoring(*boards):
	if not boards:
		boards = Board.objects.all()
	for board in boards:
		board.assign_ranks()
	Team.update_scores_and_ranks()

#Some initial teams and people
# Boards

def create_data():
	# JAZ I used this once to generate some initial data and then 
	# dumped it to YAML, from which it can be regenerated.
	# Preserved just in case.
	vanilla = Board(name="Vanilla", space=False, varying=False)
	space = Board(name="Space", space=True, varying=False)
	des = Board(name="DES", space=False, varying=True)
	euclid = Board(name="Euclid", space=True, varying=True)
	wfirst = Board(name="WFIRST", space=True, varying=False)

	vanilla.save()
	space.save()
	des.save()
	euclid.save()
	wfirst.save()

	lensfit = Team(name="Lensfit", members="Lance et al")
	ucl = Team(name="UCL-Manchester-Alliance", members="Sarah et al")
	libertarians = Team(name="RonPaul4Eva", members="Mike et al")
	nasa = Team(name="NASA", members="Jason et al")

	lensfit.save()
	ucl.save()
	libertarians.save()
	nasa.save()

	barney = User(username="barney", email="barney@example.com")
	rachel = User(username="rachel", email="rachel@example.com")
	mike = User(username="mike", email="mike@example.com")
	jaz = User.objects.get(username="jaz")

	barney.set_password('barney')
	rachel.set_password('rachel')
	mike.set_password('mike')

	barney.save()
	rachel.save()
	mike.save()
	# jaz.save()

	def add_teams(user, *teams):
		profile = user.get_profile()
		for team in teams:
			profile.teams.add(team)
		profile.save()
		user.save()

	add_teams(jaz, ucl)
	add_teams(barney, ucl, lensfit)
	add_teams(rachel, nasa)
	add_teams(mike, libertarians, nasa)

	Entry(name='nbc1', team=ucl, user=barney, board=vanilla, score=14.5).save()
	Entry(name='nbc2', team=ucl, user=jaz, board=vanilla, score=20.4).save()
	Entry(name='nbc3', team=ucl, user=barney, board=vanilla, score=884.4).save()

	Entry(name='shapelets1', team=libertarians, user=mike, board=vanilla, score=510.2).save()
	Entry(name='shapelets2', team=libertarians, user=mike, board=vanilla, score=456.4).save()

	Entry(name='deimos1', team=nasa, user=mike, board=space, score=101.2).save()
	Entry(name='deimos2', team=nasa, user=mike, board=space, score=141.4).save()

	recompute_scoring()


def save_submission_file(submission, name, notes, user, team, board):
	print "Sanity check the file size here"
	entry = Entry(team=team, name=name, notes=notes, user=user, board=board)
	entry.save()
	try:
		with open(entry.get_filename(), 'wb+') as destination:
			for chunk in submission.chunks():
				destination.write(chunk)
	except Exception as E:
		print "Could not save: %r!" % E
		entry.delete()
		return False
	return True




class MembershipRequest(models.Model):
	user = models.ForeignKey(User)
	team = models.ForeignKey(Team)
	token = models.CharField(max_length=40, unique=True)

	def generate_token(self):
		salt = hashlib.sha1(str(random.random())).hexdigest()[:5]
		username = unicode(self.user.username).encode('utf-8')
		teamname = unicode(self.team)
		self.token = hashlib.sha1(salt+username+teamname).hexdigest()
		return self.token



def user_is_member_of_team(user, team):
	teams = user.get_profile().teams.all()
	return team in teams


def too_many_entries_in_last_day(team, board):
	print "Checking"
	try:
		test_entry = Entry.objects.filter(team=team, board=board).order_by('-date')[MAXIMUM_ENTRIES_PER_DAY-1]
		print Entry.objects.filter(team=team).order_by('-date')
	except IndexError:
		return False
	one_day_ago = datetime.datetime.utcnow().replace(tzinfo=pytz.utc) - datetime.timedelta(days=1.0)
	print "here", test_entry, test_entry.date, one_day_ago
	#I know this looks odd - it does not mean "more than one day ago."
	return test_entry.date > one_day_ago


class AdminDataFile(models.Model):
	filename = models.CharField(max_length=128)
	abspath = models.CharField(max_length=512)
