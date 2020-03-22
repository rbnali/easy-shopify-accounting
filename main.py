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


SHOPIFY_CREDENTIALS = {
    "SHOPIFY_ACCESS_TOKEN": os.environ.get("SHOPIFY_ACCESS_TOKEN"),
    "SHOPIFY_PASSWORD": os.environ.get("SHOPIFY_PASSWORD"),
    "SHOPIFY_STORE": os.environ.get("SHOPIFY_STORE")
}


def connect_shopify(api_key, password, store):
    """Connect to shopify."""
    shop_url = "https://%s:%s@%s/admin" % (api_key, password, store)
    shopify.ShopifyResource.set_site(shop_url)


def get_order_page_count(date_min, date_max):
    """Get number of pages to parse."""
    counter = shopify.Order.count(updated_at_min = date_min, updated_at_max = date_max)
    pages = int((counter - (counter % 250))/250) + 1
    print('There are', counter, 'orders to retrieve.')
    return pages


def get_orders_from_page(order_list, page, date_min, date_max):
    """Get order from page and add them to order_list."""
    orders = shopify.Order.find(
        limit=250,
        page=page,
        created_at_min=date_min,
        created_at_max=date_max
    )
    for order in orders:
        order_list += [order.to_dict()]
    return order_list


def get_orders_from_all_pages(pages, date_min, date_max):
    """Get orders from pages, date_min, date_max."""
    order_list = list()
    missing_pages = list()
    for page in tqdm(range(1,pages+1)):
        try:
            order_list = get_orders_from_page(order_list, page, date_min, date_max)
        except:
            time.sleep(2)
            try:
                order_list = get_orders_from_page(order_list, page, date_min, date_max)
            except:
                missing_pages += [page]
    for page in missing_pages:
        try:
            order_list = get_orders_from_page(order_list, page, date_min, date_max)
        except Exception as e:
            print('Exception at page', p, ':', e)
    return order_list


def get_orders(api_key, password, store, date_min = '2016-12-01T00:00:00-00:00', date_max = '2050-12-01T00:00:00-00:00'):
    """Get all orders between date_min and date_max."""
    connect_shopify(api_key, password, store)
    pages = get_order_page_count(date_min, date_max)
    order_list = get_orders_from_all_pages(pages, date_min, date_max)
    df = pd.DataFrame(order_list)
    return(df)


def cleaning(row):
    """Cleaning rows of orders dataframe to match accounting format."""
    # Initialize
    d = dict(row)
    CUSTOMER_COLS = ['email', 'id']
    SHIPPING_COLS = ['address1', 'address2', 'city', 'country_code', 'first_name', 'last_name', 'zip', 'phone', 'company']
    DISCOUNT_COLS = ['code', 'amount']
    ITEM_COLS = ['title', 'quantity', 'price', 'sku', 'variant_title', 'tax_lines', 'discount_allocations']

    # Adding customer data
    d.update({k:v for k,v in row['customer'].items() if k in CUSTOMER_COLS})

    # Adding billing data
    d.update({k:v for k,v in row['billing_address'].items() if k in SHIPPING_COLS})

    # Adding discount data
    if len(row['discount_codes']) > 0:
        d.update({k:v for k,v in row['discount_codes'][0].items() if k in DISCOUNT_COLS})
    else:
        d.update({k:None for k in DISCOUNT_COLS})

    # Adding line items
    for item in row['line_items']:
        line_items = [{k:v for k,v in item.items() if k in ITEM_COLS}]
    d['line_items'] = line_items

    return(d)


def add_order_tax(row):
    """Add taxes on each order."""
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
            row_vat = 'tax_rate_%s' % (str(round(rate*100,2)))

            if (row_vat in row.index.values):
                row[row_vat] += vat
                row['price_before_taxes_'+row_vat] += price
            else:
                row[row_vat] = vat
                row['price_before_taxes_'+row_vat] = price

    except Exception as e:
        print('Got error', e, 'at row', row)

    return row


def add_shipping(row):
    """Add shipping and shipping taxes."""
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


def add_total_before_taxes(row):
    """Add total_before_taxes to each order."""
    TAX_COLS = [col for col in row.index.values if col[:4] == 'tax_rate_']
    row['total_before_taxes'] = float(row['total_price']) - row['shipping_taxes']
    for c in TAX_COLS:
        if pd.notnull(row[c]):
            row['total_before_taxes'] = row['total_before_taxes'] - row[c]
    return row


def add_payments(row):
    """Add payment method."""
    payments = row['payment_gateway_names']
    for i in range(len(payments)):
        row['payment_method_' + str(i)] = payments[i]
    return row


def add_order_summary(row):
    """Add order summary in str format."""
    row['order_summary'] = ''
    for item in row['line_items']:
        row['order_summary'] += str(item['quantity']) + ' x ' + item['sku'] + ' + '
    row['order_summary'] = row['order_summary'][:-3]
    return row


def run(api_key, password, store, start_date = '2018-01-01', end_date = '2050-12-01'):
    """
    Connects to shopify API and get all orders with accounting informations from start_date to end_date.

    Args:
        :api_key: Your API key
        :password: You password
        :store: https://yourstore.myshopify.com
        :date_min: min date of orders
        :date_max: max date of orders
    """

    # Reformat dates
    start_date += 'T00:00:00-00:00'
    end_date += 'T00:00:00-00:00'

    # Apply transformations
    orders = get_orders(api_key, password, store, date_min = start_date, date_max = end_date)
    orders = orders.apply(cleaning, axis = 1)
    orders.dropna(inplace=True)
    orders = pd.DataFrame(list(orders))
    orders = orders.drop_duplicates(subset = ['name'], keep = 'last')
    orders = orders.sort_values('created_at', axis=0)
    orders = orders[orders['name'].isnull() == False]
    orders = orders.apply(add_order_tax, axis=1)
    orders = orders.apply(add_shipping, axis=1)
    orders = orders.apply(add_total_before_taxes, axis=1)
    orders = orders.apply(add_payments, axis=1)
    orders = orders.apply(add_order_summary, axis=1)

    # Reformat columns
    orders['total_price'] = orders['total_price'].astype(float)
    orders['total_discounts'] = orders['total_discounts'].astype(float)
    orders['total_tax'] = orders['total_tax'].astype(float)

    # export
    GENERAL_COLS = ['name', 'created_at', 'total_price', 'total_before_taxes', 'total_tax', 'shipping_before_taxes', 
                'shipping_taxes','total_discounts', 'code', 'payment_method_0', 'payment_method_1', 'country_code', 
                'first_name', 'last_name', 'address1', 'address2', 'company', 'city', 'zip', 'email', 'phone', 'order_summary']
    TAX_COLS = [col for col in orders.columns if col[:4] == 'tax_rate_']
    PRICE_COLS = [col for col in orders.columns if col[:19] == 'price_before_taxes_']
    EXPORT_COLS = GENERAL_COLS + TAX_COLS + PRICE_COLS
    EXPORT_COLS = [col for col in EXPORT_COLS if col in orders.columns]
    
    return orders[EXPORT_COLS]


if __name__ == '__main__':
    # Initialize
    TODAY = datetime.date.today()
    FIRST = TODAY.replace(day=1)
    LAST_MONTH = FIRST - datetime.timedelta(days=1)
    parser = argparse.ArgumentParser()
    parser.add_argument('-start', action='store', dest='start', type=str, default = LAST_MONTH.strftime("%Y-%m-01"),
                    help='Start date to retrieve orders. Example: 2018-01-01')
    parser.add_argument('-end', action='store', dest='end', type=str, default = '2050-12-01',
                    help='End date to retrieve orders. Example: 2019-01-01')
    args = parser.parse_args()

    # Get orers
    orders = run(
        SHOPIFY_CREDENTIALS["SHOPIFY_ACCESS_TOKEN"],
        SHOPIFY_CREDENTIALS["SHOPIFY_PASSWORD"],
        SHOPIFY_CREDENTIALS["SHOPIFY_STORE"],
        args.start,
        args.end
    )

    # Save to Excel
    orders.to_excel('compta_' + args.start[:10] + '_' + args.end[:10] + '.xlsx', index=False)
