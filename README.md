# shopify-accounting

Python script to retrieve an order summary and tax information from Shopify API to Excel.

# Requirements

Please install all the necesssary requirements with the following command:

```
pip install -r requirements.txt
```

Add your shopify API credentials as environment variables:

```
export SHOPIFY_ACCESS_TOKEN=YOUR_SHOPIFY_ACCESS_TOKEN
export SHOPIFY_PASSWORD=YOUR_SHOPIFY_PASSWORD
export SHOPIFY_STORE=YOUR_SHOPIFY_STORE
```

# Arguments

Arguments       | Help
-------------   | -------------
-start          | Start date of the order import in the following format: YYYY-mm-dd
-end            | End date of the order import in the following format: YYYY-mm-dd

# Example

```
python main.py -start 2018-12-15 -end 2019-05-01
```

# Output description

Column          | Description
-------------   | -------------
name            | Name of order
created_at      | Date of creation of the order
...             | ...

More documentation on Orders fields here: https://shopify.dev/docs/admin-api/rest/reference/orders/order
