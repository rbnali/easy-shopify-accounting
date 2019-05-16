import shopify
import pandas as pd
import json
import datetime
from dateutil.relativedelta import relativedelta
from tqdm import tqdm
import numpy as np
import os
import sys
import time
import argparse

### GET ORDERS

def get_checkout_page(list_, page, API_KEY, PASSWORD, date_min, date_max):
    orders = shopify.Order.find(limit=250, page=page, created_at_min = date_min, created_at_max = date_max)
    for order in orders:
        list_ += [order.to_dict()]
    return list_

def get_orders(STORE, API_KEY, PASSWORD, date_min = '2016-12-01T00:00:00-00:00', date_max = '2050-12-01T00:00:00-00:00'):
    
    print('Uploading orders between ', date_min[0:10], ' and ', date_max[0:10])

    shop_url = "https://%s:%s@%s/admin" % (API_KEY, PASSWORD, STORE)
    shopify.ShopifyResource.set_site(shop_url)
    
    list_ = list()
    missing = list()
    counter = shopify.Order.count(updated_at_min = date_min, updated_at_max = date_max)
    print('Nb of orders to upload:', counter)
    
    pages = int((counter - (counter % 250))/250) + 1
    
    for page in tqdm(range(1,pages+1)):
        try:
            list_ = get_checkout_page(list_, page, API_KEY, PASSWORD, date_min, date_max)
        except:
            time.sleep(3)
            try:
                list_ = get_checkout_page(list_, page, API_KEY, PASSWORD, date_min, date_max)
            except:
                missing += [page]
    
    for page in missing:
        try:
            list_ = get_checkout_page(list_, page, API_KEY, PASSWORD, date_min, date_max)
        except:
            print('[ERROR] at Page ', page)
            
    df = pd.DataFrame(list_)
    return(df)


### CLEAN DATAFRAME

#### CLEAN COL CONTENT

def cleaning(row):   
    try:
        # CUSTOMER
        json_cust = row['customer']
        d1 = {k:v for k,v in json_cust.items() if k in ['email', 'id']}

        # SHIPPING ADDRESS 
        json_address = row['billing_address']
        shipping = ['address1', 'address2', 'city', 'country_code', 'first_name', 'last_name', 'zip', 'phone', 'company', 'latitude', 'longitude']
        d2 = {k:v for k,v in json_address.items() if k in shipping}

        # DISCOUNT CODES
        if (str(row['discount_codes']) != '[]'):
            json_discount = row['discount_codes'][0]
            discount = ['code', 'amount']
            d3 = {k:v for k,v in json_discount.items() if k in discount}
        else:
            d3 = {'code': '', 'amount': ''}

        # LINE ITEMS
        item_list = row['line_items']
        items_new = list()

        for i in range(len(item_list)):
            json_item = item_list[i]
            keep_item = ['title', 'quantity', 'price', 'sku', 'variant_title', 'tax_lines', 'discount_allocations']
            d_temp = {k:v for k,v in json_item.items() if k in keep_item}
            items_new += [d_temp]
            

        row['line_items'] = items_new  

        # OUTPUT
        d = dict(row)
        d.update(d1)
        d.update(d2)
        d.update(d3)
        d.pop('customer', None)
        d.pop('billing_address', None)
        d.pop('discount_codes', None)

        return(d)
    
    except Exception as e:
        print(row['name'])
        print(e)
        return(None)

#### PIVOT SKUS

def add_skus(row):
    try:
        for item in row['line_items']:
            row[item['sku']] = item['quantity']
    except: 
        print(row['line_items'])

    return row

### VAT PRODUCTS

def add_vat(row):
    try:
        rate = 0
        vat = 0
        for item in row['line_items']:
            if len(item['tax_lines']) == 0:
                rate = 0
                vat = 0
            else:
                rate = float(item['tax_lines'][0]['rate'])
                vat = float(item['tax_lines'][0]['price'])
            
            if len(item['discount_allocations']) == 0:
                discount = 0
            else:
                discount = float(item['discount_allocations'][0]['amount'])
            
            price = float(item['price'])*item['quantity'] - discount - vat
            
            row_vat = 'vat_%s' % (str(rate*100))

            if (row_vat in row.index.values):
                row[row_vat] += vat
                row['price_before_taxes_'+row_vat] += price
            else:
                row[row_vat] = vat
                row['price_before_taxes_'+row_vat] = price
        
    except Exception as e:
        print(row)
        print(e)
    
    return row

### SHIPPING

def add_shipping(row):

    shipping = float(row['total_price']) - float(row['subtotal_price'])

    if pd.notnull(row['shipping_lines']):
        if len(row['shipping_lines']) > 0:
            if len(row['shipping_lines'][0]['tax_lines']) > 0:
                row['shipping_taxes'] = float(row['shipping_lines'][0]['tax_lines'][0]['price'])
                row['shipping_before_taxes'] = shipping - row['shipping_taxes']
    else:
        row['shipping_taxes'] = 0
        row['shipping_before_taxes'] = 0

    return row

### ADD TOTAL BEFORE TAX

def add_total_before_taxes(row):
    row['total_before_taxes'] = float(row['total_price']) - row['shipping_taxes']
    print(row['total_before_taxes'])
    for c in [col for col in row.index.values if col[:4] == 'vat_']:
        if pd.notnull(row[c]):
            row['total_before_taxes'] = row['total_before_taxes'] - row[c]
    print(row['total_before_taxes'])
    return row

### PAYMENT METHODS

def add_payments(row):
    payments = row['payment_gateway_names']
    for i in range(len(payments)):
        row['payment_method_' + str(i)] = payments[i]
    return row

### ORDER CONTENT

def add_order_summary(row):
    row['order_summary'] = ''
    for item in row['line_items']:
        row['order_summary'] += str(item['quantity']) + ' x ' + item['sku'] + ' + '
    row['order_summary'] = row['order_summary'][:-3]
    return row

### RUN CODE 

def run(STORE, API_KEY,PASSWORD, start_date = '2018-01-01', end_date = '2050-12-01'):

    # ADD HOURS
    start_date += 'T00:00:00-00:00'
    end_date += 'T00:00:00-00:00'

    #### SELECT  COLUMNS
    selected_col = ['name', 'billing_address', 'created_at', 'customer','discount_codes', 'fulfillment_status',
                'id','line_items',  'subtotal_price', 'tax_lines','shipping_lines', 'total_discounts', 'total_line_items_price', 
                'total_price', 'total_tax', 'total_weight', 'updated_at', 'user_id', 'payment_gateway_names']

    ### APPLY TO DATAFRAME
    orders = get_orders(STORE, API_KEY,PASSWORD, date_min = start_date, date_max = end_date)
    orders = orders[selected_col]
    orders = orders.apply(cleaning, axis = 1)
    orders.dropna(inplace=True)
    orders = pd.DataFrame(list(orders))
    orders = orders.drop_duplicates(subset = ['name'], keep = 'last')
    orders = orders.sort_values('created_at', axis=0)
    orders = orders[orders['name'].isnull() == False]
    orders = orders.apply(add_vat, axis=1)
    orders = orders.apply(add_shipping, axis=1)
    orders = orders.apply(add_total_before_taxes, axis=1)
    orders = orders.apply(add_payments, axis=1)
    orders = orders.apply(add_order_summary, axis=1)

    ### FORMATTING
    orders['total_price'] = orders['total_price'].astype(float)
    orders['total_discounts'] = orders['total_discounts'].astype(float)
    orders['total_tax'] = orders['total_tax'].astype(float)

    ### EXPORT
    general_cols = ['name', 'created_at', 'total_price', 'total_before_taxes', 'total_tax', 'shipping_before_taxes', 
                'shipping_taxes','total_discounts', 'code', 'payment_method_0', 'payment_method_1', 'country_code', 
                'first_name', 'last_name', 'address1', 'address2', 'company', 'city', 'zip', 'email', 'phone', 'order_summary']
    tax_cols = [col for col in orders.columns if col[:4] == 'vat_']
    price_cols = [col for col in orders.columns if col[:19] == 'price_before_taxes_']
    export_cols = general_cols + tax_cols + price_cols

    export_cols = [col for col in export_cols if col in orders.columns]
    
    return orders[export_cols]


if __name__ == '__main__':

    today = datetime.date.today()
    first = today.replace(day=1)
    lastMonth = first - datetime.timedelta(days=1)

    parser = argparse.ArgumentParser()

    parser.add_argument('-store', action='store', dest='store', type=str,
                    help='Your shopify store URL')
    parser.add_argument('-api', action='store', dest='api', type=str,
                    help='Your shopify API key')
    parser.add_argument('-p', action='store', dest='password', type=str, 
                    help='Your Shopify password')
    parser.add_argument('-start', action='store', dest='start', type=str, default = lastMonth.strftime("%Y-%m-01"),
                    help='Start date to retrieve orders. Example: 2018-01-01')
    parser.add_argument('-end', action='store', dest='end', type=str, default = '2050-12-01',
                    help='End date to retrieve orders. Example: 2019-01-01')
    args = parser.parse_args()

    # RUN
    orders = run(args.store, args.api, args.password, args.start, args.end)

    # SAVE
    orders[export_cols].to_excel('compta_github_' + args.start[:10] + '_' + args.end[:10] + '.xlsx', index=False)

