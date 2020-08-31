import threading
import time
import datetime
import pandas as pd
import time
from functools import reduce, wraps
from datetime import datetime, timedelta

import model.queries as qrs
from model.HostsMetaData import HostsMetaData
import utils.helpers as hp
from utils.helpers import timer


class Singleton(type):

    defaultDT = hp.defaultTimeRange()

    def __init__(cls, name, bases, attibutes):
        cls._dict = {}

    def __call__(cls, dateFrom=None, dateTo=None):
        print(cls, dateFrom, dateTo)
        if (dateFrom is None):
            dateFrom = Singleton.defaultDT[0]
        if (dateTo is None):
            dateTo = Singleton.defaultDT[1]

        if (dateFrom, dateTo) in cls._dict:
#             print('EXISTS')
            instance = cls._dict[(dateFrom, dateTo)]
        else:
#             print('NEW', (dateFrom, dateTo))
            instance = super().__call__(dateFrom, dateTo)
            cls._dict[(dateFrom, dateTo)] = instance
        return instance


class GeneralDataLoader(object, metaclass=Singleton):

    def __init__(self, dateFrom,  dateTo):
        self.dateFrom = dateFrom
        self.dateTo = dateTo
        self.lastUpdated = None
        self.pls = pd.DataFrame()
        self.owd = pd.DataFrame()
        self.thp = pd.DataFrame()
        self.rtm = pd.DataFrame()
        self.UpdateGeneralInfo()

    @property
    def dateFrom(self):
        return self._dateFrom

    @dateFrom.setter
    def dateFrom(self, value):
        self._dateFrom = int(time.mktime(datetime.strptime(value, "%Y-%m-%d %H:%M").timetuple())*1000)

    @property
    def dateTo(self):
        return self._dateTo

    @dateTo.setter
    def dateTo(self, value):
        self._dateTo = int(time.mktime(datetime.strptime(value, "%Y-%m-%d %H:%M").timetuple())*1000)

    @property
    def lastUpdated(self):
        return self._lastUpdated

    @lastUpdated.setter
    def lastUpdated(self, value):
        self._lastUpdated = value

    @timer
    def UpdateGeneralInfo(self):
        print("last updated: {0}, new start: {1} new end: {2} ".format(self.lastUpdated, self.dateFrom, self.dateTo))

        self.pls = HostsMetaData('ps_packetloss', self.dateFrom, self.dateTo).df
        self.owd = HostsMetaData('ps_owd', self.dateFrom, self.dateTo).df
        self.thp = HostsMetaData('ps_throughput', self.dateFrom, self.dateTo).df
        self.rtm = HostsMetaData('ps_retransmits', self.dateFrom, self.dateTo).df
        self.latency_df = pd.merge(self.pls, self.owd, how='outer')
        self.throughput_df = pd.merge(self.thp, self.rtm, how='outer')
        all_df = pd.merge(self.latency_df, self.throughput_df, how='outer')
        self.all_df = all_df.drop_duplicates()

        self.pls_related_only = self.pls[self.pls['host_in_ps_meta'] == True]
        self.owd_related_only = self.owd[self.owd['host_in_ps_meta'] == True]
        self.thp_related_only = self.thp[self.thp['host_in_ps_meta'] == True]
        self.rtm_related_only = self.rtm[self.rtm['host_in_ps_meta'] == True]

        self.latency_df_related_only = self.latency_df[self.latency_df['host_in_ps_meta'] == True]
        self.throughput_df_related_only = self.throughput_df[self.throughput_df['host_in_ps_meta'] == True]
        self.all_df_related_only = self.all_df[self.all_df['host_in_ps_meta'] == True]

        self.lastUpdated = datetime.now()
        self.StartGenInfoThread()

    def StartGenInfoThread(self):
        self.lastUpdated = datetime.now().strftime("%d-%m-%Y, %H:%M")
        # Update dates
        defaultDT = hp.defaultTimeRange()
        if (self.lastUpdated != defaultDT[1]):
            self.dateFrom = defaultDT[0]
            self.dateTo = defaultDT[1]
        self.thread = threading.Timer(24*60*60, self.UpdateGeneralInfo)

        self.thread.daemon = True
        self.thread.start()



class SiteDataLoader():

    genData = GeneralDataLoader()

    def __init__(self):
        self.UpdateSiteData()

    def UpdateSiteData(self):
        print('UpdateSiteData >>> ', self.genData.dateFrom, self.genData.dateTo)
        pls_site_in_out = self.InOutDf("ps_packetloss", self.genData.pls_related_only)
        self.pls_data = pls_site_in_out['data']
        self.pls_dates = pls_site_in_out['dates']
        owd_site_in_out = self.InOutDf("ps_owd", self.genData.owd_related_only)
        self.owd_data = owd_site_in_out['data']
        self.owd_dates = owd_site_in_out['dates']
        thp_site_in_out = self.InOutDf("ps_throughput", self.genData.thp_related_only)
        self.thp_data = thp_site_in_out['data']
        self.thp_dates = thp_site_in_out['dates']
        rtm_site_in_out = self.InOutDf("ps_retransmits", self.genData.rtm_related_only)
        self.rtm_data = rtm_site_in_out['data']
        self.rtm_dates = rtm_site_in_out['dates']

        self.latency_df_related_only = self.genData.latency_df_related_only
        self.throughput_df_related_only = self.genData.throughput_df_related_only

        self.sites = self.orderSites()
        self.StartThread()

    def StartThread(self):
        print('Active threads:',threading.active_count())
        self.thread = threading.Timer(3600.0, self.UpdateSiteData)
        self.thread.daemon = True
        self.thread.start()

    @timer
    def InOutDf(self, idx, idx_df):
        in_out_values = []

        for t in ['dest_host', 'src_host']:
            meta_df = idx_df.copy()

            df = pd.DataFrame(qrs.queryDailyAvg(idx, t, self.genData.dateFrom, self.genData.dateTo)).reset_index()

            df['index'] = pd.to_datetime(df['index'], unit='ms').dt.strftime('%d/%m')
            df = df.transpose()
            header = df.iloc[0]
            df = df[1:]
            df.columns = ['day-3', 'day-2', 'day-1', 'day']

            meta_df = pd.merge(meta_df, df, left_on="host", right_index=True)

            three_days_ago = meta_df.groupby('site').agg({'day-3': lambda x: x.mean(skipna=False)}, axis=1).reset_index()
            two_days_ago = meta_df.groupby('site').agg({'day-2': lambda x: x.mean(skipna=False)}, axis=1).reset_index()
            one_day_ago = meta_df.groupby('site').agg({'day-1': lambda x: x.mean(skipna=False)}, axis=1).reset_index()
            today = meta_df.groupby('site').agg({'day': lambda x: x.mean(skipna=False)}, axis=1).reset_index()

            site_avg_df = reduce(lambda x,y: pd.merge(x,y, on='site', how='outer'), [three_days_ago, two_days_ago, one_day_ago, today])
            site_avg_df.set_index('site', inplace=True)
            change = site_avg_df.pct_change(axis='columns')
            site_avg_df = pd.merge(site_avg_df, change, left_index=True, right_index=True, suffixes=('_val', ''))
            site_avg_df['direction'] = 'IN' if t == 'dest_host' else 'OUT'

            in_out_values.append(site_avg_df)

        site_df = pd.concat(in_out_values).reset_index()
        site_df = site_df.round(2)

        return {"data": site_df,
                "dates": header}

    def orderSites(self):
        problematic = []
        problematic.extend(self.thp_data.nsmallest(20, ['day-3_val', 'day-2_val', 'day-1_val', 'day_val'])['site'].values)
        problematic.extend(self.rtm_data.nlargest(20, ['day-3_val', 'day-2_val', 'day-1_val', 'day_val'])['site'].values)
        problematic.extend(self.pls_data.nlargest(20, ['day-3_val', 'day-2_val', 'day-1_val', 'day_val'])['site'].values)
        problematic.extend(self.owd_data.nlargest(20, ['day-3_val', 'day-2_val', 'day-1_val', 'day_val'])['site'].values)
        problematic = list(set(problematic))
        all_df = self.genData.all_df_related_only.copy()
        all_df['has_problems'] = all_df['site'].apply(lambda x: True if x in problematic else False)
        sites = all_df.sort_values(by='has_problems', ascending=False).drop_duplicates(['site'])['site'].values
        return sites
