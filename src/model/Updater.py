import gc
import os
import os.path
import time
import threading
import traceback

from utils.parquet import Parquet
from model.Alarms import Alarms
import utils.helpers as hp
from utils.helpers import timer
import model.queries as qrs
import pandas as pd
import pickle

from ml.create_thrpt_dataset import createThrptDataset
from ml.thrpt_dataset_model_train import trainMLmodel
from ml.create_packet_loss_dataset import createPcktDataset
from ml.packet_loss_one_month_onehot import one_month_data
from ml.packet_loss_train_model import packet_loss_train_model
import os
from datetime import datetime, timedelta
import psconfig.api


@timer
class ParquetUpdater(object):
    
    def __init__(self, location='parquet/'):
        self.pq = Parquet()
        self.alarms = Alarms()
        self.location = location
        required_folders = ['raw', 'frames', 'pivot', 'ml-datasets']
        self.createLocation(required_folders)

        try:
            if not self.__isDataFresh(required_folders):
                print("Updating...")
                self.storeMetaData()
                self.cacheIndexData()
                self.storeAlarms()
                self.storeASNPathChanged()

                # self.storeThroughputDataAndModel()
                # self.storePacketLossDataAndModel()
                self.psConfigData()

            # Set the schedulers
            Scheduler(60*60*12, self.storeMetaData)
            Scheduler(60*60, self.cacheIndexData)

            Scheduler(60*30, self.storeAlarms)
            Scheduler(60*60*12, self.storeASNPathChanged)
            Scheduler(60*60*24, self.psConfigData)


            # Scheduler(60*60*12, self.storeThroughputDataAndModel)
            # Scheduler(60*60*12, self.storePacketLossDataAndModel)
        except Exception as e:
            print(traceback.format_exc())


    # The following function is used to group alarms by site 
    # taking into account the most recent 48 hours only
    def groupAlarms(self, pivotFrames):
        dateFrom, dateTo = hp.defaultTimeRange(days=2)
        metaDf = self.pq.readFile('parquet/raw/metaDf.parquet')
        # frames, pivotFrames = self.alarms.loadData(dateFrom, dateTo)

        nodes = metaDf[~(metaDf['site'].isnull()) & (metaDf['site'] != '')\
               & (metaDf['lat'] != '') & (metaDf['lat'].isnull()==False)].drop_duplicates()
        lat_lon_count = nodes.groupby(['site', 'lat', 'lon']).size().reset_index(name='count')
        # Find the most common lat-lon for each site
        most_common_lat_lon = lat_lon_count.loc[lat_lon_count.groupby('site')['count'].idxmax()]

        alarmCnt = []
        
        for site, lat, lon in most_common_lat_lon[['site', 'lat', 'lon']].values.tolist():
            for e, df in pivotFrames.items():
                # column "to" is closest to the time the alarms was generated, 
                # thus we want to which approx. when the alarms was created,
                # to be between dateFrom and dateTo
                df['to'] = pd.to_datetime(df['to'], utc=True)
                sdf = df[(df['tag'] == site) & (df['to'] >= dateFrom) & (df['to'] <= dateTo)]
                
                if len(sdf) > 0:
                    # sdf['id'].unique() returns the number of unique alarms for the given site
                    # those are the documents generated and stored in ES. They can be found in frames folder
                    # While pivotFrames expands the alarms to the level of individual sites
                    entry = {"event": e, "site": site, 'cnt':  len(sdf['id'].unique()),
                            "lat": lat, "lon": lon}
                else:
                    entry = {"event": e, "site": site, 'cnt': 0,
                            "lat": lat, "lon": lon}
                alarmCnt.append(entry)

        print('Number of sites:', len(alarmCnt))
        alarmsGrouped = pd.DataFrame(alarmCnt)
        print('Number of site-alarms:', len(alarmsGrouped[alarmsGrouped['cnt']>0]))

        self.pq.writeToFile(alarmsGrouped, f'{self.location}alarmsGrouped.parquet')


    def __isDataFresh(self, required_folders, freshness_threshold=1*60*60): # 1 hour
        """
        Check if the data in the specified location is fresh.
        :param location: The directory to check.
        :param freshness_threshold: The freshness threshold in seconds (default is 1 hour).
        :return: True if the data is fresh, False otherwise.
        """
        current_time = time.time()
        
        for folder in required_folders:
            folder_path = os.path.join(self.location, folder)
            print(f"Checking folder: {folder_path}")
            if not os.listdir(folder_path):
                print(f"Folder {folder_path} is empty.")
                return False

        for root, dirs, files in os.walk(self.location):
            for file in files:
                file_path = os.path.join(root, file)
                file_mod_time = os.path.getmtime(file_path)
                file_age = current_time - file_mod_time
                print(f"File: {file_path}, Age: {file_age} seconds")
                if file_age > freshness_threshold:
                    print(f"File {file_path} is older than the freshness threshold.")
                    return False

        print("All files are fresh.")
        return True


    @timer
    def queryData(self, idx, dateFrom, dateTo):
        intv = int(hp.CalcMinutes4Period(dateFrom, dateTo)/30)
        if idx in ['ps_throughput']:
            dateFrom, dateTo = hp.defaultTimeRange(days=21)
            intv = 42  # 12 hour bins

        data = []
        
        time_list = hp.GetTimeRanges(dateFrom, dateTo, intv)
        for i in range(len(time_list)-1):
            data.extend(qrs.query4Avg(idx, time_list[i], time_list[i+1]))

        return data


    @timer
    def cacheIndexData(self):
        dateFrom, dateTo = hp.defaultTimeRange(1)
        INDICES = ['ps_packetloss', 'ps_owd', 'ps_throughput']
        measures = pd.DataFrame()
        for idx in INDICES:
            df = pd.DataFrame(self.queryData(idx, dateFrom, dateTo))
            # pq.writeToFile(df, f'{location}{idx}.parquet')
            df.loc[:, 'src'] = df['src'].str.upper()
            df.loc[:, 'dest'] = df['dest'].str.upper()
            df.loc[:, 'src_site'] = df['src_site'].str.upper()
            df.loc[:, 'dest_site'] = df['dest_site'].str.upper()
            df['idx'] = idx
            measures = pd.concat([measures, df])
        self.pq.writeToFile(measures, f'{self.location}raw/measures.parquet')

    @timer
    def storeMetaData(self):
        metaDf = qrs.getMetaData()
        self.pq.writeToFile(metaDf, f"{self.location}raw/metaDf.parquet")

    @timer
    def psConfigData(self):
        mesh_url = "https://psconfig.aglt2.org/pub/config"
        mesh_config = psconfig.api.PSConfig(mesh_url)
        all_hosts = mesh_config.get_all_hosts()
        host_test_type = pd.DataFrame({
                                        'host': list(all_hosts),
                                        'owd': False,
                                        'trace': False,
                                        'throughput': False
                                        })
        def checkTestsForHost(host, mesh_conf):
            """
            Classifies the host as belonging to one of
            the three test groups (latency, trace and throughput).
            """
            try:
                types = mesh_conf.get_test_types(host)
            except Exception:
                return False, False
            latency = any(test in ['latency', 'latencybg'] for test in types)
            trace = 'trace' in types
            throughput = any(test in ['throughput', 'rtt'] for test in types) # as rtt is now in ps_throughput
            return host, latency, trace, throughput
        
        host_test_type = host_test_type['host'].apply(
            lambda host: pd.Series(checkTestsForHost(host, mesh_config))
        )
        host_test_type.columns = ['host', 'owd', 'trace', 'throughput']
        self.pq.writeToFile(host_test_type, f"{self.location}raw/psConfigData.parquet")
        
    @timer
    def storeAlarms(self):
        dateFrom, dateTo = hp.defaultTimeRange(30)
        print("Update data. Get all alarms for the past 30 days...", dateFrom, dateTo)
        frames, pivotFrames = self.alarms.getAllAlarms(dateFrom, dateTo)
        self.groupAlarms(pivotFrames)

        for event,df in pivotFrames.items():
            if event == 'ASN path anomalies per site':
                print(df.info())
                # df['all_alarm_ids_src'] = df['all_alarm_ids_src'].eval()
            filename = self.alarms.eventCF(event)
            fdf = frames[event]
            if len(fdf)>0:
                self.pq.writeToFile(df, f"parquet/pivot/{filename}.parquet")
                self.pq.writeToFile(fdf, f"parquet/frames/{filename}.parquet")

    @timer
    def storeASNPathChanged(self):
        dateFrom, dateTo = hp.defaultTimeRange(days=3)
        df = qrs.queryPathAnomaliesDetails(dateFrom, dateTo)
        self.pq.writeToFile(df, f"parquet/asn_path_changes.parquet")

    def createLocation(self, required_folders):

        if os.path.isdir(self.location):
            print(self.location,"exists.")
        else:
            print(self.location, "doesn't exists. Creating...")
            os.mkdir(self.location)

        for folder in required_folders:
            folder_path = os.path.join(self.location, folder)
            if not os.path.isdir(folder_path):
                print(folder_path, "doesn't exists. Creating...")
                os.mkdir(folder_path)


    @timer
    def storeThroughputDataAndModel(self):
        print('Starting storeThroughputDataAndModel')
        now = hp.defaultTimeRange(days=90, datesOnly=True)
        start_date = now[0]
        end_date = now[1]
        start_date, end_date = [f'{start_date}T00:01:00.000Z', f'{end_date}T23:59:59.000Z']

        rawDf = createThrptDataset(start_date, end_date)

        self.pq.writeToFile(rawDf, f'{self.location}ml-datasets/throughput_Df.parquet')

        # train the ML model on the loaded dataset
        rawDf_onehot, model = trainMLmodel(rawDf)
        del rawDf
        print('Trained ML model')

        self.pq.writeToFile(rawDf_onehot, f'{self.location}ml-datasets/throughput_onehot_Df.parquet')
        # save the classification model as a pickle file
        model_pkl_file = f'{self.location}ml-datasets/XGB_Classifier_model_throughput.pkl'
        with open(model_pkl_file, 'wb') as file:
            pickle.dump(model, file)
        print('Saved XGB_Classifier_model_throughput.pkl')
        del rawDf_onehot, model
        gc.collect()


    @timer
    def storePacketLossDataAndModel(self):
        start_time = time.time()
        print("Starting storePacketLossDataAndModel")
        now = hp.defaultTimeRange(days=60, datesOnly=True)
        start_date = now[0]
        end_date = now[1]
        start_date, end_date = [f'{start_date}T00:01:00.000Z', f'{end_date}T23:59:59.000Z']

        plsDf = createPcktDataset(start_date, end_date)
        self.pq.writeToFile(plsDf, f'{self.location}ml-datasets/packet_loss_Df.parquet')

        print("One-hot encoding the dataset")
        plsDf_onehot_month, plsDf_onehot = one_month_data(plsDf)
        self.pq.writeToFile(plsDf_onehot, f'{self.location}ml-datasets/packet_loss_onehot_Df.parquet')
        del plsDf_onehot

        print("Training the model on one month data")
        model = packet_loss_train_model(plsDf_onehot_month)
        del plsDf_onehot_month

        print("Saving the classification model as a pickle file")
        model_pkl_file = f'{self.location}ml-datasets/XGB_Classifier_model_packet_loss.pkl'
        with open(model_pkl_file, 'wb') as file:
            pickle.dump(model, file)
        del plsDf_onehot, model
        gc.collect()
        end_time = time.time()
        print(f"Finished storePacketLossDataAndModel in {end_time - start_time} seconds")


class Scheduler(object):
    def __init__(self, interval, function, *args, **kwargs):
        self._timer = None
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        self.next_call = time.time()
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
        if not self.is_running:
            self.next_call += self.interval
            self._timer = threading.Timer(self.next_call - time.time(), self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        if self._timer:
            self._timer.cancel()
        self.is_running = False
