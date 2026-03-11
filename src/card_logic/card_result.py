"""Card result processing"""
import copy
import numpy
from src import constants
from src.logger import create_logger
from src.card_logic.utils import get_card_colors, field_process_sort

logger = create_logger()

class CardResult:
    """This class processes a card list and produces results based on a list of fields (i.e., ALSA, GIHWR, COLORS, etc.)"""

    def __init__(self, set_metrics, tier_data, configuration, pick_number):
        self.metrics = set_metrics
        self.tier_data = tier_data
        self.configuration = configuration
        self.pick_number = pick_number

    def return_results(self, card_list, colors, fields):
        """This function processes a card list and returns a list with the requested field results"""
        return_list = []
        wheel_sum = 0
        if constants.DATA_FIELD_WHEEL in fields:
            wheel_sum = self.__retrieve_wheel_sum(card_list)

        for card in card_list:
            try:
                selected_card = copy.deepcopy(card)
                selected_card["results"] = ["NA"] * len(fields)

                for count, option in enumerate(fields):
                    if constants.FILTER_OPTION_TIER in option:
                        selected_card["results"][count] = self.__process_tier(
                            card, option)
                    elif option == constants.DATA_FIELD_COLORS:
                        selected_card["results"][count] = self.__process_colors(
                            card)
                    elif option == constants.DATA_FIELD_WHEEL:
                        selected_card["results"][count] = self.__process_wheel_normalized(
                            card, wheel_sum)
                    elif option in [constants.DATA_FIELD_BEST_GPWR, constants.DATA_FIELD_BEST_GIHWR]:
                        selected_card["results"][count] = self.__process_best_in_field(
                            card, option)
                    elif option in card:
                        selected_card["results"][count] = card[option]
                    else:
                        selected_card["results"][count] = self.__process_filter_fields(
                            card, option, colors)

                return_list.append(selected_card)
            except Exception as error:
                logger.error(error)
        return return_list

    def __process_tier(self, card, option):
        """Retrieve tier list rating for this card"""
        result = "NA"
        try:
            card_name = card[constants.DATA_FIELD_NAME].replace('///', '//')
            if card_name in self.tier_data[option].ratings:
                tier_data = self.tier_data[option].ratings[card_name]
                result = tier_data.rating
                # Append an asterisk to denote a comment
                result = "*" + result if tier_data.comment else result
        except Exception as error:
            logger.error(error)

        return result

    def __process_colors(self, card):
        """Retrieve card colors based on color identity (includes kicker, abilities, etc.) or mana cost"""
        try:
            # Use color identity if enabled or handle lands (mana cost cannot determine colors)
            if self.configuration.settings.color_identity_enabled or constants.CARD_TYPE_LAND in card[constants.DATA_FIELD_TYPES]:
                return "".join(sorted(
                    card[constants.DATA_FIELD_COLORS],
                    key=constants.CARD_COLORS.index
                ))

            # Fallback: determine colors based on mana cost
            return "".join(get_card_colors(card[constants.DATA_FIELD_MANA_COST]).keys())
        
        except Exception as error:
            logger.error(error)
            return "NA"

    def __retrieve_wheel_sum(self, card_list):
        """Calculate the sum of all wheel percentage values for the card list"""
        total_sum = 0

        for card in card_list:
            total_sum += self.__process_wheel(card)

        return total_sum

    def __process_wheel(self, card):
        """Calculate wheel percentage"""
        result = constants.RESULT_UNKNOWN_VALUE

        try:
            # TODO: Adjust this if pack is a play booster and/or contains basic lands
            # Only calculate if there is a possibility that you may see playable cards from this pack again
            if self.pick_number <= len(constants.WHEEL_COEFFICIENTS):
                # 0 is treated as pick 1 for PremierDraft P1P1
                self.pick_number = max(self.pick_number, 1)
                alsa = card[constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS][constants.DATA_FIELD_ALSA]
                
                # TODO: How are these coefficients derived/useful?
                coefficients = constants.WHEEL_COEFFICIENTS[self.pick_number - 1]
                # Exclude ALSA values below 2. These should not be assumed to wheel
                result = round(numpy.polyval(coefficients, alsa),
                               1) if alsa >= 2 else constants.RESULT_UNKNOWN_VALUE
                result = max(result, constants.RESULT_UNKNOWN_VALUE)
        except Exception as error:
            logger.error(error)

        return result

    def __process_wheel_normalized(self, card, total_sum):
        """Calculate the normalized wheel percentage using the sum of all percentages within the card list"""
        result = constants.RESULT_UNKNOWN_VALUE

        try:
            result = self.__process_wheel(card)

            result = round((result / total_sum)*100, 1) if total_sum > 0 else 0
        except Exception as error:
            logger.error(error)

        return result

    def __process_filter_fields(self, card, option, colors):
        """Retrieve win rate result based on the application settings"""
        result = "NA"

        try:
            rated_colors = []
            for color in colors:
                if constants.DATA_FIELD_DECK_COLORS in card \
                        and color in card[constants.DATA_FIELD_DECK_COLORS] \
                        and option in card[constants.DATA_FIELD_DECK_COLORS][color]:
                    if option in constants.WIN_RATE_OPTIONS:
                        rating_data = self.__format_win_rate(card,
                                                             option,
                                                             constants.WIN_RATE_FIELDS_DICT[option],
                                                             color)
                        rated_colors.append(rating_data)
                    else:  # Field that's not a win rate (ALSA, IWD, etc)
                        result = card[constants.DATA_FIELD_DECK_COLORS][color][option]
                        result = constants.RESULT_UNKNOWN_STRING if result == 0.0 else result
            if rated_colors:
                result = sorted(
                    rated_colors, key=field_process_sort, reverse=True)[0]
        except Exception as error:
            logger.error(error)

        return result

    def __process_best_in_field(self, card, option):
        """Retrieve the best performing color for the specified field (GPWR or GIHWR)"""
        result = "NA"
        try:
            target_field = constants.DATA_FIELD_GPWR if option == constants.DATA_FIELD_BEST_GPWR else constants.DATA_FIELD_GIHWR
            count_field = constants.WIN_RATE_FIELDS_DICT[target_field]
            
            best_value = -1
            best_formatted_result = "NA"
            best_color = "NA"
            
            # Calculate total games for dynamic filtering
            total_games = 0
            if constants.DATA_FIELD_DECK_COLORS in card:
                # Try to get total games from "All Decks" first
                if constants.FILTER_OPTION_ALL_DECKS in card[constants.DATA_FIELD_DECK_COLORS] and \
                   count_field in card[constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]:
                    total_games = card[constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS][count_field]
                else:
                    # Fallback: sum individual colors
                    for color, data in card[constants.DATA_FIELD_DECK_COLORS].items():
                        if color != constants.FILTER_OPTION_ALL_DECKS and count_field in data:
                            total_games += data[count_field]

            if constants.DATA_FIELD_DECK_COLORS in card:
                for color, data in card[constants.DATA_FIELD_DECK_COLORS].items():
                    # Ignore "All Decks" and check if the target field exists
                    if color != constants.FILTER_OPTION_ALL_DECKS and target_field in data and count_field in data:
                        
                        # Dynamic Filtering: Ignore if < threshold% of total games or < 10 games
                        game_count = data[count_field]
                        threshold = self.configuration.settings.best_in_column_threshold / 100.0
                        if game_count < 10 or (total_games > 0 and (game_count / total_games) < threshold):
                            continue

                        # Calculate the formatted result (Rating, Grade, or %)
                        formatted_result = self.__format_win_rate(card, target_field, count_field, color)
                        
                        # Get a sortable numeric value
                        sortable_value = field_process_sort(formatted_result)
                        
                        if sortable_value > best_value:
                            best_value = sortable_value
                            best_formatted_result = formatted_result
                            best_color = color
            
            if best_color != "NA":
                result = f"{best_formatted_result} ({best_color})"
                
        except Exception as error:
            logger.error(error)
            
        return result

    def __format_win_rate(self, card, winrate_field, winrate_count, color):
        """The function will return a grade, rating, or win rate depending on the application's Result Format setting"""
        result = 0

        # Force Rating format for specific win-rate fields when a deck filter is active
        deck_filter = self.configuration.settings.deck_filter
        if (deck_filter not in (constants.FILTER_OPTION_ALL_DECKS, constants.FILTER_OPTION_AUTO)
                and winrate_field in constants.FORCED_RATING_WIN_RATE_FIELDS):
            effective_format = constants.RESULT_FORMAT_RATING
        else:
            effective_format = self.configuration.settings.result_format

        # Produce a result that matches the effective format
        if effective_format == constants.RESULT_FORMAT_RATING:
            result = self.__card_rating(
                card, winrate_field, winrate_count, color)
        elif effective_format == constants.RESULT_FORMAT_GRADE:
            result = self.__card_grade(
                card, winrate_field, winrate_count, color)
        else:
            result = card[constants.DATA_FIELD_DECK_COLORS][color][winrate_field]
        result = constants.RESULT_UNKNOWN_STRING if result == constants.RESULT_UNKNOWN_VALUE else result

        return result

    def __card_rating(self, card, winrate_field, winrate_count, color):
        """The function will take a card's win rate and calculate a 5-point rating"""
        result = constants.RESULT_UNKNOWN_VALUE
        try:
            winrate = card[constants.DATA_FIELD_DECK_COLORS][color][winrate_field]

            mean, std = self.metrics.get_metrics(color, winrate_field)
            deviation_list = list(constants.GRADE_DEVIATION_DICT.values())
            upper_limit = mean + \
                std * deviation_list[0]
            lower_limit = mean + \
                std * deviation_list[-1]

            if (winrate != 0) and (upper_limit != lower_limit):
                result = round(
                    ((winrate - lower_limit) / (upper_limit - lower_limit)) * 5.0, 1)
                result = min(result, 5.0)
                result = max(result, 0.1)

        except Exception as error:
            logger.error(error)
        return result

    def __card_grade(self, card, winrate_field, winrate_count, color):
        """The function will take a card's win rate and assign a letter grade based on the number of standard deviations from the mean"""
        result = constants.LETTER_GRADE_NA
        try:
            winrate = card[constants.DATA_FIELD_DECK_COLORS][color][winrate_field]
            
            mean, std = self.metrics.get_metrics(color, winrate_field)
            if ((winrate != 0) and (std != 0)):
                result = constants.LETTER_GRADE_F
                for grade, deviation in constants.GRADE_DEVIATION_DICT.items():
                    standard_score = (winrate - mean) / std
                    if standard_score >= deviation:
                        result = grade
                        break

        except Exception as error:
            logger.error(error)
        return result
