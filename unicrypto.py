import os
import re
import json
import urllib3
from timeit import default_timer as timer
# import fitz
import sys
import coinaddrvalidator
from attrs import asdict
from openpyxl import load_workbook
import argparse
from datetime import datetime
from pathlib import Path
import pandas as pd
from termcolor import colored

reDict = {
            'btc': r'([1][a-zA-HJ-NP-Z0-9]{25,39})|(3[a-zA-HJ-NP-Z0-9]{33})|([bc|bcrt|tb]1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{3,71})',
            'bch': r'((bitcoincash|bchtest):[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{42})',
            'eth': r'(0x[A-Fa-f0-9]{40})',
            'ltc': r'([LM3][a-km-zA-HJ-NP-Z1-9]{26,33})',
            'doge': r'(D{1}[5-9A-HJ-NP-U]{1}[1-9A-HJ-NP-Za-km-z]{32})',
            'dash': r'(X[1-9A-HJ-NP-Za-km-z]{33})',
            'xmr': r'(4[0-9AB][1-9A-HJ-NP-Za-km-z]{93})',
            'neo': r'(A[0-9a-zA-Z]{33})',
            'xrp': r'([xr][a-zA-HJ-NP-Z0-9]{25,46})'
        }


def parseArgs():
    coins = ', '.join(reDict.keys())
    parser = argparse.ArgumentParser(description='parse files or folders [recursively] for crypto addresses!', epilog=f'currently supported coins: {coins}')
    parser.add_argument('-e', '--enrich', action='store_true', dest='e', required=False, help='perform API lookup of BTC, BCH, and ETH address(es)')
    parser.add_argument('-i', '--input', nargs='?', dest='i', required=True, type=Path, help='file or folder to be parsed')
    return parser.parse_args(sys.argv[1:])


def getCurrentBalance(address, symbol):
    http = urllib3.PoolManager()
    url = f'https://api.blockcypher.com/v1/{symbol}/main/addrs/{address}'
    response = http.request('GET', url)
    # check if rate limit exceeded (200 requests/hr)
    if response.status == '429':
        return False
    return json.loads(response.data)


def getFiles(inputPath):
    inputPathList = []
    try:
        for entry in os.scandir(inputPath):
            if entry.is_file() and 'DS_Store' not in entry.name.lower():
                inputPathList.append(entry.path)
        print(colored(f'Processing directory: {inputPath}\n', 'yellow'))
        return inputPathList
    except NotADirectoryError:
        return inputPath.split()


class helperRoutines:
    
    def getAddresses(textIn):
        addresses = set()
        resultList = []
        for key, value in reDict.items():
            for match in re.finditer(value, textIn):
                if match[0] not in addresses:
                    try:
                        validResult = asdict(coinaddrvalidator.validate(key.lower(), match[0].encode('utf-8')))
                        if validResult['valid']:
                            result = {
                                'name': validResult['name'],
                                'symbol': validResult['ticker'],
                                'address': validResult['address'].decode(),
                                'network': validResult['network'],
                                'extended': validResult['is_extended'],
                                'type': validResult['address_type']
                            }
                            addresses.add(match[0])
                            resultList.append(result)
                    except TypeError:
                        pass
        return resultList, addresses
        
    def parsePDF(inputPath):
        pdfDoc = fitz.open(inputPath)
        numPages = pdfDoc.page_count
        pdfText = ''
        for page in pdfDoc.pages(0, numPages):
            pdfText += page.get_text('text')
        return pdfText

    def parseExcel(inputPath):
        wb = load_workbook(inputPath, data_only=True)
        excelText = ''
        for sheet in wb.worksheets:
            active = sheet.values
            for row in active:
                for value in row:
                    if value:
                        excelText += (str(value) + ',')
        return excelText

    def parseText(inputPath):
        with open(inputPath, 'r', errors='replace') as inFile:
            textText = inFile.read()
            return textText


def getEnrichment(outputJsonList):
    
    def getValue():
        http = urllib3.PoolManager()
        url = 'https://api.coinbase.com/v2/exchange-rates?currency=USD'
        response = http.request('GET', url)
        data = json.loads(response.data)['data']['rates']
        coinVals = {
            'btc': float(data['BTC']),
            'bch': float(data['BCH']),
            'eth': float(data['ETH']),
            'ltc': float(data['LTC']),
            'doge': float(data['DOGE']),
            'dash': float(data['DASH']),
            'xrp': float(data['XRP'])  
        }
        return coinVals
    
    coinVals = getValue()
    coinRates = {
        'btc': 100000000,
        'bch': 100000000,
        'eth': 1000000000,
        'ltc': 100000000,
        'doge': 1,
        'dash': 100000000,
        'xrp': 1
    }
    
    print('\nQuerying API for found addresses [this may take a while!]...')
    
    addressList = []
    addressSet = set()
    
    # make unique list of addresses for submission to API
    for outputJson in outputJsonList['tasks']:
        for result in outputJson['found_stat']:
            if result['address'] not in addressSet:
                addressList.append({
                    'address': result['address'],
                    'symbol': result['symbol']
                })
                addressSet.add(result['address'])
    
    enrichDataList = []
    SUCCESS = 1
    for address in addressSet:
        for addressObj in addressList:
            if address == addressObj['address'] and addressObj['symbol'].endswith(('btc', 'bch', 'eth', 'ltc', 'doge', 'dash')):
                # success ensures that rate limit has not been exceeded
                if SUCCESS:
                    try:
                        data = getCurrentBalance(addressObj['address'], addressObj['symbol'])
                        if data:
                            enrichData = {
                                'address': data['address'],
                                'total_received': data['total_received'],
                                'total_sent': data['total_sent'],
                                'balance': round(data['balance'] / coinRates[addressObj['symbol']], 10),
                            }
                            enrichData['balance_usd'] = round(enrichData['balance'] / coinVals[addressObj['symbol']], 2)
                            enrichData['n_tx'] =  data['n_tx']
                            enrichDataList.append(enrichData)
                        else:
                            print('[!] Rate limit exceeded for API requests! Future requests will be skipped.')
                            SUCCESS = 0
                    except KeyError:
                        pass
                else:
                    break
                
    outputData = {
        'address': [],
        'total_received': [],
        'total_sent': [],
        'balance': [],
        'balance_usd': [],
        'n_tx': []
    }
    
    for outputJson in outputJsonList['tasks']:
        for result in outputJson['found_stat']:
            for enrichData in enrichDataList:
                if result['address'] == enrichData['address']:
                    result.update({'enrich_data': [enrichData]})
            # extract only enrichment data for stdout display
            if 'enrich_data' in result.keys():
                for data in result['enrich_data']:
                    if data['address'] not in outputData['address']:
                        for key, value in data.items():
                            if key == 'balance_usd':
                                outputData[key].append('${:,}'.format(value))
                            else:
                                outputData[key].append(value)
    
    if outputData['address']:
        disLen = len(outputData['address'])
        if disLen > 10:
            disLen = 10
        print(f'\nTop {disLen} wallets by balance [max 10]:')
        df = pd.DataFrame(outputData).sort_values(by=['balance'], ascending=False).head(10)
        df.reset_index(drop=True, inplace=True)
        print(df)
        
    return outputJsonList


def prepareOutput(outputJsonList, numAddys):
    getOutput = input(colored('\nEnter output file path [leave blank to save in root of target directory]: ', 'yellow'))
    if not getOutput:
        if os.path.isdir(args.i):
            outFile = os.path.join(args.i, '_extracted_crypto.json')
        else:
            outFile = os.path.join(os.path.split(args.i)[0], '_extracted_crypto.json')
    else:
        try:
            # make sure the entered path is valid
            file = open(getOutput, 'w')
            outFile = getOutput
            file.close()
        except (FileNotFoundError, PermissionError):
            print('\nWhoops! Looks like that folder is invalid or you lack permission to write to it.\nSaving results to root of uniCrypto!')
    try:
        with open(outFile, 'w') as fileOut:
            fileOut.write(json.dumps(outputJsonList, indent=4))
    except PermissionError:
        with open(os.path.join(Path(__file__).parent.resolve(), '_extracted_crypto.json'), 'w') as fileOut:
            fileOut.write(json.dumps(outputJsonList, indent=4))
    print(f'\nComplete! Processed {numAddys} address(es) in {round(timer() - start, 2)} seconds.')
    print(colored(f'\nOutput saved to {outFile}\n', 'green'))


def fileHandler(inputPath):
    if inputPath.endswith('pdf'):
        return helperRoutines.parsePDF(inputPath)
    if inputPath.endswith(('.xls', '.xlsx')):
        return helperRoutines.parseExcel(inputPath)
    else:
        return helperRoutines.parseText(inputPath)
    
    
def main():
    global start, args
    args = parseArgs()
    start = timer()
    inputValues = getFiles(os.path.normpath(args.i))
    outputJsonList = {
        'job': os.path.normpath(args.i),
        'tasks': []
    }
    numFiles = len(inputValues)
    addresses = set()
    print('Progress\t\t\t\tFilename')
    for i, inputPath in enumerate(inputValues):
        fileName = os.path.split(inputPath)[1]
        print(f'[+] Processing file {i} / {numFiles}, {round((i / numFiles) * 100, 2)}%:\t{fileName}')
        textIn = fileHandler(inputPath)
        resultList, address = helperRoutines.getAddresses(textIn)
        addresses.update(address)
        if resultList:
            outputJson = {
                'file_name': os.path.split(inputPath)[1].lower(),
                'file_size': os.stat(inputPath).st_size,
                'c_time': datetime.fromtimestamp(os.stat(inputPath).st_ctime_ns / 1000000000).strftime('%Y-%m-%d %H:%M:%S UTC'),
                'm_time': datetime.fromtimestamp(os.stat(inputPath).st_mtime_ns / 1000000000).strftime('%Y-%m-%d %H:%M:%S UTC'),
                'a_time': datetime.fromtimestamp(os.stat(inputPath).st_atime_ns / 1000000000).strftime('%Y-%m-%d %H:%M:%S UTC'),
                'char_count': len(textIn),
                'found_stat': resultList
                }
            outputJsonList['tasks'].append(outputJson)
    if outputJsonList['tasks']:
        print(f'\nFound {len(addresses)} valid addresses within dataset.')
        if args.e:
            outputJson = getEnrichment(outputJsonList)
            prepareOutput(outputJson, len(addresses))
        else:
            prepareOutput(outputJsonList, len(addresses))
        

if __name__ == '__main__':
    
    main()
    
    