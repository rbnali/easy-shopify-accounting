# shopify-accounting
Python script to retrieve an order summary and tax information from Shopify API to Excel.

# Requirements

Please install all the necesssary requirements with the following command:

```
pip install -r requirements.txt
```


# Arguments

Arguments       | Help
-------------   | -------------
-store          | Your Shopify store url, for instance: storeurl.myshopify.com
-api            | Your Shopify API accesss token
-p              | Your Shopify API password
-start          | Start date of the order import in the following format: YYYY-mm-dd
-end            | End date of the order import in the following format: YYYY-mm-dd

# Example

```
python retrieve.py -store mystore.myshopify.com -api MY_API_KEY -p MY_PASS -start 2018-12-15 -end 2019-05-01
```

# Output description

Column          | Description
-------------   | -------------
name            | Name of order
created_at      | Date of creation of the order

...
