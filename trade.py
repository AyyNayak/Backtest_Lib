import pandas as pd
import talib
import matplotlib.pyplot as plt
from util import resample, write_trades, write_result
import csv
import os
from statistics import mean
import numpy as np
import datetime
from tqdm import tqdm


def make_long(longs, dataframe, row, lots=10, overlap=False, target=900, stop=300, max_lots=10):
    # longs is a set of all longs
    # dataframe is a pandas dataframe of asks, used to market exit positions
    # row has our timestamp, entry price at row[0] and row[1] respectively

    # we need to iterate through the dataframe such that when target or stop == open we must close trade

    # check if there is an existing long trade (trade overlap)
    timestamp_of_entry = row[0]
    current_lots = 0
    # print(timestamp_of_entry)
    if overlap is not True:
        # CASE OF NO PYRAMIDING
        if len(longs) != 0:
            for trade in longs:
                if "timestamp_of_exit" in list(trade.keys()) and trade["timestamp_of_exit"] is not None:
                    if timestamp_of_entry < trade["timestamp_of_exit"]:
                        return {"timestamp_of_entry": timestamp_of_entry,
                                "timestamp_of_exit": None,
                                "entry_price": None,
                                "target_price": None,
                                "stop_price": None,
                                "type_of_exit": "Overlap",
                                "pnl": None,
                                "open_lots": current_lots * lots}
    else:
        # CASE OF PYRAMIDING
        if len(longs) != 0:
            for trade in longs:
                if "timestamp_of_exit" in list(trade.keys()) and trade["timestamp_of_exit"] is not None:
                    if (timestamp_of_entry < trade["timestamp_of_exit"]) and \
                            (timestamp_of_entry > trade["timestamp_of_entry"]):
                        current_lots += 1

    if current_lots * lots >= max_lots:
        return {"timestamp_of_entry": timestamp_of_entry,
                "timestamp_of_exit": None,
                "entry_price": None,
                "target_price": None,
                "stop_price": None,
                "type_of_exit": "Lot limit",
                "pnl": None,
                "open_lots": current_lots * lots}

    # This part of the code will be unreachable if there is a trade overlap
    entry_price = row[1]['close']
    target_price = entry_price + target  # 9 rupees up for crude
    stop_price = entry_price - stop  # 3 rupees down for crude
    timestamp_of_exit = None
    type_of_exit = None
    pnl = 0

    # type of exit and PNL calculation
    for item in dataframe.iterrows():
        if item[0] > timestamp_of_entry:
            current_price = item[1]['open']
            if current_price >= target_price:  # If target is hit
                type_of_exit = "Win"
                pnl = ((current_price - entry_price) * lots * 100)
                timestamp_of_exit = item[0]
                break
            elif current_price <= stop_price:  # If stop is hit
                type_of_exit = "Loss"
                pnl = ((current_price - entry_price) * lots * 100)
                timestamp_of_exit = item[0]
                break
    # print(pnl)
    return {"timestamp_of_entry": timestamp_of_entry,
            "timestamp_of_exit": timestamp_of_exit,
            "entry_price": entry_price,
            "target_price": target_price,
            "stop_price": stop_price,
            "type_of_exit": type_of_exit,
            "pnl": pnl,
            "open_lots": current_lots * lots}


def make_short(shorts, dataframe, row, lots=10, overlap=False, target=900, stop=300, max_lots=10):
    # shorts is a set of all shorts
    # dataframe is a pandas dataframe of bids, used to market exit positions
    # row has our timestamp, entry price at row[0] and row[1] respectively

    # we need to iterate through the dataframe such that when target or stop == open we must close trade

    # check if there is an existing long trade (trade overlap)
    timestamp_of_entry = row[0]
    current_lots = 0
    # print(timestamp_of_entry)
    if overlap is not True:
        if len(shorts) != 0:
            for trade in shorts:
                if "timestamp_of_exit" in list(trade.keys()):
                    if "timestamp_of_exit" in list(trade.keys()) and trade["timestamp_of_exit"] is not None:
                        return {"timestamp_of_entry": timestamp_of_entry,
                                "timestamp_of_exit": None,
                                "entry_price": None,
                                "target_price": None,
                                "stop_price": None,
                                "type_of_exit": "Overlap",
                                "pnl": 0.00,
                                "open_lots": current_lots * lots
                                }
    else:
        # CASE OF PYRAMIDING
        if len(shorts) != 0:
            for trade in shorts:
                if "timestamp_of_exit" in list(trade.keys()) and trade["timestamp_of_exit"] is not None:
                    if (timestamp_of_entry < trade["timestamp_of_exit"]) and \
                            (timestamp_of_entry > trade["timestamp_of_entry"]):
                        current_lots += 1

    if current_lots * lots >= max_lots:
        return {"timestamp_of_entry": timestamp_of_entry,
                "timestamp_of_exit": None,
                "entry_price": None,
                "target_price": None,
                "stop_price": None,
                "type_of_exit": "Lot limit",
                "pnl": None,
                "open_lots": -1 * current_lots * lots}

    # This part of the code will be unreachable if there is a trade overlap
    entry_price = row[1]['close']
    target_price = entry_price - target  # 9 rupees down for crude
    stop_price = entry_price + stop  # 3 rupees up for crude
    timestamp_of_exit = None
    type_of_exit = None
    pnl = 0

    # type of exit and PNL calculation
    for item in dataframe.iterrows():
        if item[0] > timestamp_of_entry:
            current_price = item[1]['open']
            if current_price <= target_price:  # If target is hit
                type_of_exit = "Win"
                pnl = (current_price - entry_price) * lots * (-1) * 100
                timestamp_of_exit = item[0]
                break
            elif current_price >= stop_price:  # If stop is hit
                type_of_exit = "Loss"
                pnl = (current_price - entry_price) * lots * (-1) * 100
                timestamp_of_exit = item[0]
                break

    # print(pnl)
    return {"timestamp_of_entry": timestamp_of_entry,
            "timestamp_of_exit": timestamp_of_exit,
            "entry_price": entry_price,
            "target_price": target_price,
            "stop_price": stop_price,
            "type_of_exit": type_of_exit,
            "pnl": pnl,
            "open_lots": -1 * current_lots * lots}


def do_backtest(bid, ask, rsi_windows, rsi_oversold_bounds, rsi_overbought_bounds, ema_values, targets, stops,
                overlaps, lots, max_lots, filename_parent):
    print("Doing {}".format(filename_parent))

    i = 0
    results = []
    for overlap in overlaps:
        for rsi_window in rsi_windows:
            for rsi_upper in rsi_overbought_bounds:
                for rsi_lower in rsi_oversold_bounds:
                    for slow_ema in ema_values:
                        # if slow_ema > fast_ema:
                        #     break
                        for fast_ema in ema_values:
                            if slow_ema < fast_ema:
                                break
                            for target in targets:
                                # if stop > target:
                                #     break
                                for stop in stops:
                                    if stop > target:
                                        break

                                    settings = "overlap_{}-rsiwindow_{}-rsiupper_{}-rsilower_{}-slowema_{}-fastema_{}-target_{}-stop_{}".format(
                                        overlap, rsi_window, rsi_upper, rsi_lower, slow_ema, fast_ema, target, stop)
                                    # print(settings)
                                    ask['RSI'] = talib.RSI(ask['close'], timeperiod=rsi_window)
                                    ask['MA_fast'] = talib.EMA(ask['close'], timeperiod=fast_ema)
                                    ask['MA_slow'] = talib.EMA(ask['close'], timeperiod=slow_ema)

                                    longs = []
                                    shorts = []

                                    # \ STRATEGY
                                    # Return type is a dict with
                                    # if valid : {timestamp of entry, timestamp of exit, entry price, target price, stop price, type of exit, pnl}
                                    # if invalid : {timestamp_of_entry, type_of_exit}
                                    # print(row[1]['RSI']) # RSI VALUES HERE, row[0] is index (timestamp)

                                    for row in ask.iterrows():
                                        if row[1]['MA_fast'] > row[1]['MA_slow']:
                                            if row[1]['RSI'] < rsi_lower:  # Oversold condition
                                                longs.append(
                                                    make_long(longs, bid, row, lots=lots, target=target, stop=stop,
                                                              overlap=overlap, max_lots=max_lots))
                                        if row[1]['MA_fast'] < row[1]['MA_slow']:
                                            if row[1]['RSI'] > rsi_upper:  # Overbought condition
                                                shorts.append(
                                                    make_short(shorts, ask, row, lots=lots, target=target,
                                                               stop=stop,
                                                               overlap=overlap, max_lots=max_lots))
                                    if len(longs) == 0 or len(shorts) == 0:
                                        break
                                    num_longs, num_shorts = 0, 0
                                    for item in longs:
                                        if item["type_of_exit"] in ["Win", "Loss"]:
                                            num_longs += 1
                                    for item in shorts:
                                        if item["type_of_exit"] in ["Win", "Loss"]:
                                            num_shorts += 1

                                    if num_shorts == 0:
                                        break
                                    if num_longs == 0:
                                        break
                                    # / STRATEGY

                                    # PNL Calc
                                    # PNL for longs

                                    longs_pnl = 0
                                    long_turnover = 0
                                    for item in longs:
                                        try:
                                            longs_pnl += item["pnl"]
                                            long_turnover += item["entry_price"] * lots
                                        except:
                                            pass
                                    long_brokerage = long_turnover / 1000000000 * 838
                                    net_long_pnl = longs_pnl - long_brokerage

                                    # PNL for shorts
                                    shorts_pnl = 0
                                    short_turnover = 0

                                    for item in shorts:
                                        try:
                                            shorts_pnl += item['pnl']
                                            short_turnover += item["entry_price"] * lots
                                        except:
                                            pass

                                    short_brokerage = short_turnover / 1000000000 * 838
                                    net_short_pnl = shorts_pnl - short_brokerage
                                    # print("Net PNL long is: " + str(net_long_pnl) + " and Net PNL short is: " + str(net_short_pnl))

                                    if net_long_pnl + net_short_pnl < -6000:
                                        # print("Bad PNL in {}, skipped".format(settings))
                                        break

                                    long_win, long_loss, short_win, short_loss = 0, 0, 0, 0
                                    for item in longs:
                                        if item["type_of_exit"] == "Win":
                                            long_win += 1
                                        if item["type_of_exit"] == "Loss":
                                            long_loss += 1

                                    for item in shorts:
                                        if item["type_of_exit"] == "Win":
                                            short_win += 1
                                        if item["type_of_exit"] == "Loss":
                                            short_loss += 1

                                    profitability_longs = long_win / num_longs
                                    profitability_shorts = short_win / num_shorts
                                    profitability_total = (long_win + short_win) / (num_longs + num_shorts)

                                    total_time_for_every_trade = []
                                    for item in longs:
                                        try:
                                            total_time_for_every_trade.append(
                                                item["timestamp_of_exit"] - item["timestamp_of_entry"])
                                        except:
                                            pass
                                    for item in shorts:
                                        try:
                                            total_time_for_every_trade.append(
                                                item["timestamp_of_exit"] - item["timestamp_of_entry"])
                                        except:
                                            pass

                                    avg_time = sum(total_time_for_every_trade, datetime.timedelta(0)) / len(
                                        total_time_for_every_trade)

                                    net_pnl_list = []

                                    for item in longs:
                                        if "pnl" in list(item.keys()):
                                            if item["pnl"] is not None:
                                                net_pnl_list.append(item["pnl"])
                                    for item in shorts:
                                        if "pnl" in list(item.keys()):
                                            if item["pnl"] is not None:
                                                net_pnl_list.append(item["pnl"])

                                    max_pnl = max(net_pnl_list)
                                    max_dd = min(net_pnl_list)
                                    avg_pnl = mean(net_pnl_list)

                                    longs_concurrent = []
                                    for item in longs:
                                        longs_concurrent.append(item["open_lots"])
                                    shorts_concurrent = []
                                    for item in shorts:
                                        shorts_concurrent.append(item["open_lots"])

                                    # Logic to return data as a result
                                    if net_long_pnl != 0.0:
                                        if net_short_pnl != 0.0:
                                            results.append({"settings": settings,
                                                            "netlongpnl": net_long_pnl,
                                                            "netshortpnl": net_short_pnl,
                                                            "netpnl": net_short_pnl + net_long_pnl,
                                                            "profitability_longs": profitability_longs,
                                                            "profitability_shorts": profitability_shorts,
                                                            "profitability_total": profitability_total,
                                                            "number_of_trades": num_shorts + num_longs,
                                                            "num_longs": num_longs,
                                                            "num_shorts": num_shorts,
                                                            "max_profit": max_pnl,
                                                            "max_DD": max_dd,
                                                            "average_pnl": avg_pnl,
                                                            "apnl/max_DD": avg_pnl / abs(max_dd),
                                                            "average_trade_time": avg_time,
                                                            "long_max_concurrent": max(longs_concurrent),
                                                            "short_max_concurrent": min(shorts_concurrent),
                                                            })
                                    # i += 1
                                    # print(str(i) + " : " + str(profitability_total) + " : " + str(
                                    #     net_short_pnl + net_long_pnl) + " : " + str(
                                    #     num_longs + num_shorts) + " : " + settings)
                                    # List of all trades
                                    trades = longs + shorts
                                    write_trades(settings, trades, filename_parent)
    return results


def get_default_backtest(bid_file, ask_file):
    bid = pd.read_csv(bid_file)
    bid.set_index(["Timestamp"], drop=True, inplace=True)
    ask = pd.read_csv(ask_file)
    ask.set_index(["Timestamp"], drop=True, inplace=True)
    rsi_windows = range(7, 36, 7)  # 5
    rsi_oversold_bounds = range(15, 50, 5)  # 7
    rsi_overbought_bounds = range(50, 85, 5)  # 7
    ema_values = range(7, 43, 7)  # 6
    targets = range(800, 1700, 200)  # 8
    stops = [800, 1000]  # 2
    overlaps = [True]  # 0
    # lots = int(input("Enter number of lots per signal\n"))
    # max_lots = int(input("Enter number of maximum lots open at any given time\n"))

    lots, max_lots = 1, 10

    results = do_backtest(bid, ask, rsi_windows, rsi_oversold_bounds, rsi_overbought_bounds, ema_values, targets,
                          stops,
                          overlaps, lots, max_lots, filename_parent=bid_file)

    status = write_result(results, bid_file)
    return status


def ohlc_backtest(bid, ask, rsi_windows, rsi_oversold_bounds, rsi_overbought_bounds, ema_values, targets, stops,
                  overlaps, lots, max_lots, filename_parent):
    i = 0
    results = []
    for overlap in overlaps:
        for rsi_window in rsi_windows:
            for rsi_upper in rsi_overbought_bounds:
                for rsi_lower in rsi_oversold_bounds:
                    for slow_ema in ema_values:
                        # if slow_ema > fast_ema:
                        #     break
                        for fast_ema in ema_values:
                            if slow_ema <= fast_ema:
                                break
                            if slow_ema < 28:
                                break
                            if fast_ema > 15:
                                break
                            for target in targets:
                                # if stop > target:
                                #     break
                                for stop in stops:
                                    if stop >= target:
                                        break
                                    # print(ask.tail(1).index)
                                    settings = "overlap_{}-rsiwindow_{}-rsiupper_{}-rsilower_{}-slowema_{}-fastema_{}-target_{}-stop_{}".format(
                                        overlap, rsi_window, rsi_upper, rsi_lower, slow_ema, fast_ema, target, stop)
                                    print("At setting : " + settings)
                                    ask['RSI'] = talib.RSI(ask['close'], timeperiod=rsi_window)
                                    ask['MA_fast'] = talib.EMA(ask['close'], timeperiod=fast_ema)
                                    ask['MA_slow'] = talib.EMA(ask['close'], timeperiod=slow_ema)
                                    ask.to_csv("a.csv")
                                    longs = []
                                    shorts = []
                                    # print(ask.tail(5)['RSI'])
                                    # \ STRATEGY
                                    # Return type is a dict with
                                    # if valid : {timestamp of entry, timestamp of exit, entry price, target price, stop price, type of exit, pnl}
                                    # if invalid : {timestamp_of_entry, type_of_exit}
                                    # print(row[1]['RSI']) # RSI VALUES HERE, row[0] is index (timestamp)
                                    print("Bridged 1")
                                    for row in ask.iterrows():
                                        if row[1]['MA_fast'] > row[1]['MA_slow']:
                                            if row[1]['RSI'] < rsi_lower:  # Oversold condition
                                                longs.append(
                                                    make_long(longs, bid, row, lots=lots, target=target, stop=stop,
                                                              overlap=overlap, max_lots=max_lots))
                                        if row[1]['MA_fast'] < row[1]['MA_slow']:
                                            if row[1]['RSI'] > rsi_upper:  # Overbought condition
                                                shorts.append(
                                                    make_short(shorts, ask, row, lots=lots, target=target,
                                                               stop=stop,
                                                               overlap=overlap, max_lots=max_lots))
                                    print("Bridge 2 : " + str(len(longs)) + " : " + str(len(shorts)))

                                    if len(longs) == 0 or len(shorts) == 0:
                                        break
                                    num_longs, num_shorts = 0, 0
                                    for item in longs:
                                        if item["type_of_exit"] in ["Win", "Loss"]:
                                            num_longs += 1
                                    for item in shorts:
                                        if item["type_of_exit"] in ["Win", "Loss"]:
                                            num_shorts += 1
                                    print("Bridge 3")
                                    if num_shorts == 0:
                                        break
                                    if num_longs == 0:
                                        break
                                    # / STRATEGY
                                    print("Bridge 4")
                                    # PNL Calc
                                    # PNL for longs

                                    longs_pnl = 0
                                    long_turnover = 0
                                    for item in longs:
                                        try:
                                            longs_pnl += item["pnl"]
                                            long_turnover += item["entry_price"]
                                        except:
                                            pass
                                    long_brokerage = long_turnover / 1000000000 * 838
                                    net_long_pnl = longs_pnl - long_brokerage

                                    # PNL for shorts
                                    shorts_pnl = 0
                                    short_turnover = 0
                                    print("Bridge 5")
                                    for item in shorts:
                                        try:
                                            shorts_pnl += item['pnl']
                                            short_turnover += item["entry_price"]
                                        except:
                                            pass

                                    short_brokerage = short_turnover / 1000000000 * 838
                                    net_short_pnl = shorts_pnl - short_brokerage
                                    # print("Net PNL long is: " + str(net_long_pnl) + " and Net PNL short is: " + str(net_short_pnl))

                                    # if net_long_pnl+net_short_pnl < -6000:
                                    #     # print("Bad PNL in {}, skipped".format(settings))
                                    #     break
                                    print("Bridge 6")
                                    long_win, long_loss, short_win, short_loss = 0, 0, 0, 0
                                    for item in longs:
                                        if item["type_of_exit"] == "Win":
                                            long_win += 1
                                        if item["type_of_exit"] == "Loss":
                                            long_loss += 1

                                    for item in shorts:
                                        if item["type_of_exit"] == "Win":
                                            short_win += 1
                                        if item["type_of_exit"] == "Loss":
                                            short_loss += 1

                                    profitability_longs = long_win / num_longs
                                    profitability_shorts = short_win / num_shorts
                                    profitability_total = (long_win + short_win) / (num_longs + num_shorts)
                                    print("Bridge 7")

                                    if profitability_total < 0.3 or (net_short_pnl + net_long_pnl) < 0:
                                        print("Bad profitability, skipped\n")
                                        break

                                    total_time_for_every_trade = []
                                    for item in longs:
                                        if item["timestamp_of_exit"] is not None and item["timestamp_of_entry"] is not None:
                                            duration = pd.to_datetime(item["timestamp_of_exit"]) - pd.to_datetime(item["timestamp_of_entry"])
                                            print(duration)
                                            total_time_for_every_trade.append(duration)

                                    for item in shorts:
                                        if item["timestamp_of_exit"] is not None and item[
                                            "timestamp_of_entry"] is not None:
                                            duration = pd.to_datetime(item["timestamp_of_exit"]) - pd.to_datetime(
                                                item["timestamp_of_entry"])
                                            print(duration)
                                            total_time_for_every_trade.append(duration)

                                    print("Bridge 8")

                                    print(total_time_for_every_trade)

                                    avg_time = sum(total_time_for_every_trade, datetime.timedelta(0)) / len(
                                        total_time_for_every_trade)

                                    net_pnl_list = []

                                    for item in longs:
                                        if "pnl" in list(item.keys()):
                                            if item["pnl"] is not None:
                                                net_pnl_list.append(item["pnl"])
                                    for item in shorts:
                                        if "pnl" in list(item.keys()):
                                            if item["pnl"] is not None:
                                                net_pnl_list.append(item["pnl"])
                                    print("Bridge 9")

                                    max_pnl = max(net_pnl_list)
                                    max_dd = min(net_pnl_list)
                                    avg_pnl = mean(net_pnl_list)

                                    longs_concurrent = []
                                    for item in longs:
                                        longs_concurrent.append(item["open_lots"])
                                    shorts_concurrent = []
                                    for item in shorts:
                                        shorts_concurrent.append(item["open_lots"])
                                    print("End bridge")

                                    # Logic to return data as a result
                                    if net_long_pnl != 0.0:
                                        if net_short_pnl != 0.0:
                                            results.append({"settings": settings,
                                                            "netlongpnl": net_long_pnl,
                                                            "netshortpnl": net_short_pnl,
                                                            "netpnl": net_short_pnl + net_long_pnl,
                                                            "profitability_longs": profitability_longs,
                                                            "profitability_shorts": profitability_shorts,
                                                            "profitability_total": profitability_total,
                                                            "number_of_trades": num_shorts + num_longs,
                                                            "num_longs": num_longs,
                                                            "num_shorts": num_shorts,
                                                            "max_profit": max_pnl,
                                                            "max_DD": max_dd,
                                                            "average_pnl": avg_pnl,
                                                            "apnl/max_DD": avg_pnl / abs(max_dd),
                                                            "average_trade_time": avg_time,
                                                            "long_max_concurrent": max(longs_concurrent),
                                                            "short_max_concurrent": min(shorts_concurrent),
                                                            })
                                    i += 1
                                    print(str(i) + " : " + str(profitability_total) + " : " + str(
                                        net_short_pnl + net_long_pnl) + " : " + str(
                                        num_longs + num_shorts) + " : " + settings)
                                    # List of all trades
                                    trades = longs + shorts
                                    write_trades(settings, trades, filename_parent)
    return results

