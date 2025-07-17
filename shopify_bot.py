#Currently working the best

import os
import streamlit as st
import requests
from openai import OpenAI
from dotenv import load_dotenv
import re

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SHOPIFY_ADMIN_API_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN")
SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL")

# Initialize OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Shopify headers
headers = {
    "X-Shopify-Access-Token": SHOPIFY_ADMIN_API_TOKEN,
    "Content-Type": "application/json"
}

# Session state setup
for key in [
    "conversation", "awaiting_clarification", "clarification_type",
    "clarification_data", "original_query", "original_product", "clarified_variant"
]:
    if key not in st.session_state:
        st.session_state[key] = [] if "conversation" in key or "clarification_data" in key else False if "awaiting" in key else ""


# Extract product intent
def extract_product_intent(query):
    prompt = f"""
From the query below, extract:
1. product_name_or_sku (string) - can be SKU, part number, P/N, or product title keywords
2. requested_info (list of fields like price, cost, inventory, dimensions, profit, margin)

Note: SKU can also be referred to as "part number" or "P/N"

Respond as JSON:
{{"product_name_or_sku": "...", "requested_info": ["...", "..."]}}

Query: "{query}"
"""
    response = openai_client.chat.completions.create(
        model="gpt-4", messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=300
    )
    try:
        return eval(response.choices[0].message.content.strip())
    except:
        return None


# Extract comparison intent
def extract_comparison_intent(query):
    prompt = f"""
From the query below, determine if this is a comparison query and extract:
1. is_comparison (boolean)
2. product1_name_or_sku (string)
3. product2_name_or_sku (string)
4. requested_info (list of fields like price, cost, inventory, dimensions, profit, margin)

Look for keywords like "compare", "vs", "versus", "difference between", "and" connecting two products.

Respond as JSON:
{{"is_comparison": true/false, "product1_name_or_sku": "...", "product2_name_or_sku": "...", "requested_info": ["...", "..."]}}

Query: "{query}"
"""
    response = openai_client.chat.completions.create(
        model="gpt-4", messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=300
    )
    try:
        result = eval(response.choices[0].message.content.strip())
        return result
    except Exception as e:
        # print(f"Error parsing comparison intent: {e}")  # Debug print
        return None


# ENHANCED: Extract status and category based queries
def extract_status_and_category_intent(query):
    """Extract intent for status and category-based queries"""
    query_lower = query.lower()
    
    # Simple keyword detection
    status_keywords = {
        'draft': 'DRAFT',
        'active': 'ACTIVE', 
        'archived': 'ARCHIVED',
        'published': 'ACTIVE',
        'unpublished': 'DRAFT'
    }
    
    # Category keywords and patterns
    category_patterns = [
        r'categorized as [\'"]([^\'"]+)[\'"]',
        r'category [\'"]([^\'"]+)[\'"]',
        r'in category [\'"]([^\'"]+)[\'"]',
        r'with category [\'"]([^\'"]+)[\'"]',
        r'type [\'"]([^\'"]+)[\'"]',
        r'product type [\'"]([^\'"]+)[\'"]'
    ]
    
    # Check for status-related patterns
    is_status_query = False
    is_category_query = False
    status_value = ""
    category_value = ""
    query_type = "list"
    
    # Detect status
    if "status" in query_lower:
        is_status_query = True
        for keyword, status in status_keywords.items():
            if keyword in query_lower:
                status_value = status
                break
    
    # Detect category
    if any(word in query_lower for word in ['category', 'categorized', 'type', 'product type']):
        is_category_query = True
        # Try to extract category value using regex patterns
        for pattern in category_patterns:
            match = re.search(pattern, query_lower)
            if match:
                category_value = match.group(1).strip()
                break
        
        # If no quoted category found, try common category names
        if not category_value:
            common_categories = ['uncategorized', 'wine', 'spirits', 'beer', 'accessories', 'gift']
            for cat in common_categories:
                if cat in query_lower:
                    category_value = cat
                    break
    
    # Determine query type
    if "how many" in query_lower or "count" in query_lower:
        query_type = "count"
    elif "list" in query_lower or "show" in query_lower or "which" in query_lower:
        query_type = "list"
    
    # Use GPT as fallback for complex queries
    if (is_status_query and not status_value) or (is_category_query and not category_value):
        prompt = f"""
From the query below, extract:
1. status_value (one of: DRAFT, ACTIVE, ARCHIVED, or empty string if not mentioned)
2. category_value (the product category/type mentioned, or empty string if not mentioned)

Query: "{query}"

Examples:
- "Which products have status 'Draft' and are categorized as 'Uncategorized'?" 
  -> status_value: "DRAFT", category_value: "Uncategorized"
- "How many active wine products?"
  -> status_value: "ACTIVE", category_value: "wine"
- "List all draft products"
  -> status_value: "DRAFT", category_value: ""

Respond as JSON:
{{"status_value": "...", "category_value": "..."}}
"""
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4", messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=200
            )
            result = eval(response.choices[0].message.content.strip())
            if result.get("status_value"):
                status_value = result["status_value"]
                is_status_query = True
            if result.get("category_value"):
                category_value = result["category_value"]
                is_category_query = True
        except:
            pass
    
    return {
        "is_status_query": is_status_query,
        "is_category_query": is_category_query,
        "status_value": status_value,
        "category_value": category_value,
        "query_type": query_type,
        "is_combined_query": is_status_query and is_category_query
    }

def extract_date_intent(query):
    """Extract date-based query intent"""
    query_lower = query.lower()
    
    # Check for date-related keywords
    date_keywords = ['created after', 'created before', 'created on', 'after', 'before', 'since']
    is_date_query = any(keyword in query_lower for keyword in date_keywords)
    
    if not is_date_query:
        return None
    
    # Use GPT to extract date information
    prompt = f"""
From the query below, extract:
1. date_condition (one of: "after", "before", "on")
2. date_value (in YYYY-MM-DD format)
3. query_type (one of: "list", "count")

Examples:
- "List products created after August 1, 2024" -> date_condition: "after", date_value: "2024-08-01", query_type: "list"
- "How many products were created before January 15, 2024?" -> date_condition: "before", date_value: "2024-01-15", query_type: "count"
- "Show products created on December 1, 2023" -> date_condition: "on", date_value: "2023-12-01", query_type: "list"

Query: "{query}"

Respond as JSON:
{{"date_condition": "...", "date_value": "...", "query_type": "..."}}
"""
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4", 
            messages=[{"role": "user", "content": prompt}], 
            temperature=0, 
            max_tokens=200
        )
        result = eval(response.choices[0].message.content.strip())
        return result
    except:
        return None
    

# NEW: Fetch inventory item details for cost, profit, and margin
def fetch_inventory_item_details(inventory_item_id):
    """Fetch cost, profit, and margin from inventory item"""
    query = f"""
    {{
      inventoryItem(id: "{inventory_item_id}") {{
        id
        unitCost {{
          amount
          currencyCode
        }}
        tracked
        sku
      }}
    }}
    """
    
    response = requests.post(
        f"https://{SHOPIFY_STORE_URL}/admin/api/2023-07/graphql.json",
        headers=headers,
        json={"query": query}
    )
    
    result = response.json()
    return result.get("data", {}).get("inventoryItem", {})


# NEW: Calculate profit and margin
def calculate_profit_and_margin(cost, price):
    """Calculate profit and margin from cost and price"""
    try:
        cost_float = float(cost) if cost and cost != "N/A" else 0
        price_float = float(price) if price and price != "N/A" else 0
        
        if cost_float == 0 or price_float == 0:
            return {"profit": "N/A", "margin": "N/A"}
        
        profit = price_float - cost_float
        margin = (profit / price_float) * 100
        
        return {
            "profit": f"{profit:.2f}",
            "margin": f"{margin:.2f}%"
        }
    except (ValueError, TypeError, ZeroDivisionError):
        return {"profit": "N/A", "margin": "N/A"}


# Clarify which variant and what info
def extract_variant_intent(user_input, variants):
    variant_titles = [v["node"]["title"] for v in variants]
    variant_list_str = "\n".join(f"- {title}" for title in variant_titles)
    prompt = f"""
You are helping identify which variant the user means and what info they want.

Variants:
{variant_list_str}

User query: "{user_input}"

Return JSON like:
{{"matched_variant_title": "exact title", "requested_info": ["cost", "price", "profit", "margin"]}}

If uncertain, return:
{{"matched_variant_title": null, "requested_info": []}}
"""
    response = openai_client.chat.completions.create(
        model="gpt-4", messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=300
    )
    try:
        return eval(response.choices[0].message.content.strip())
    except:
        return {"matched_variant_title": None, "requested_info": []}


# ENHANCED: Search products by status and/or category
def search_products_by_criteria(status=None, category=None):
    """Search for products with specific status and/or category"""
    
    # Build query conditions
    query_conditions = []
    
    if status:
        query_conditions.append(f"status:{status}")
    
    if category:
        # Try both product_type and tag fields for category matching
        query_conditions.append(f"(product_type:{category} OR tag:{category})")
    
    # Combine conditions with AND
    query_string = " AND ".join(query_conditions) if query_conditions else "*"
    
    query = f"""
    {{
      products(first: 100, query: "{query_string}") {{
        edges {{
          node {{
            id
            title
            handle
            status
            productType
            tags
            createdAt
            updatedAt
            vendor
          }}
        }}
      }}
    }}
    """
    
    # print(f"GraphQL Query: {query}")  # Debug print
    
    response = requests.post(
        f"https://{SHOPIFY_STORE_URL}/admin/api/2023-07/graphql.json",
        headers=headers,
        json={"query": query}
    )
    
    result = response.json()
    # print(f"API Response: {result}")  # Debug print
    
    return result

def search_products_by_date(date_condition, date_value):
    """Search for products based on creation date"""
    
    # Convert date condition to GraphQL format
    if date_condition == "after":
        date_filter = f"created_at:>{date_value}"
    elif date_condition == "before":
        date_filter = f"created_at:<{date_value}"
    elif date_condition == "on":
        date_filter = f"created_at:{date_value}"
    else:
        return {"data": {"products": {"edges": []}}}
    
    query = f"""
    {{
      products(first: 100, query: "{date_filter}") {{
        edges {{
          node {{
            id
            title
            handle
            status
            productType
            tags
            createdAt
            updatedAt
            vendor
          }}
        }}
      }}
    }}
    """
    
    # print(f"Date GraphQL Query: {query}")  # Debug print
    
    response = requests.post(
        f"https://{SHOPIFY_STORE_URL}/admin/api/2023-07/graphql.json",
        headers=headers,
        json={"query": query}
    )
    
    result = response.json()
    # print(f"Date API Response: {result}")  # Debug print
    
    return result

# Search Shopify products with fuzzy matching
def search_products(query_string):
    query = f"""
    {{
      products(first: 10, query: "title:{query_string} OR sku:{query_string} OR tag:{query_string}") {{
        edges {{
          node {{
            id
            title
            handle
          }}
        }}
      }}
    }}
    """
    response = requests.post(
        f"https://{SHOPIFY_STORE_URL}/admin/api/2023-07/graphql.json",
        headers=headers,
        json={"query": query}
    )
    result = response.json()
    products = result.get("data", {}).get("products", {}).get("edges", [])
    
    if not products:
        words = query_string.split()
        search_terms = []
        for word in words:
            if len(word) >= 2:
                search_terms.append(f"title:*{word}*")
                search_terms.append(f"sku:*{word}*")
        search_terms.append(f"title:*{query_string}*")
        search_terms.append(f"sku:*{query_string}*")
        
        fuzzy_query = f"""
        {{
          products(first: 20, query: "{' OR '.join(search_terms)}") {{
            edges {{
              node {{
                id
                title
                handle
              }}
            }}
          }}
        }}
        """
        
        response = requests.post(
            f"https://{SHOPIFY_STORE_URL}/admin/api/2023-07/graphql.json",
            headers=headers,
            json={"query": fuzzy_query}
        )
        result = response.json()
    
    return result


# UPDATED: Fetch product details by GID with inventory item information
def fetch_product_details_by_gid(gid):
    query = f"""
    {{
      product(id: "{gid}") {{
        title
        handle
        createdAt
        status
        vendor
        productType
        tags
        onlineStoreUrl
        metafields(first: 20) {{
          edges {{
            node {{
              namespace
              key
              value
            }}
          }}
        }}
        variants(first: 10) {{
          edges {{
            node {{
              id
              sku
              title
              price
              inventoryQuantity
              inventoryItem {{
                id
                unitCost {{
                  amount
                  currencyCode
                }}
                tracked
              }}
            }}
          }}
        }}
        images(first: 1) {{
          edges {{
            node {{
              url
              altText
            }}
          }}
        }}
      }}
    }}
    """
    response = requests.post(
        f"https://{SHOPIFY_STORE_URL}/admin/api/2023-07/graphql.json",
        headers=headers,
        json={"query": query}
    )
    return response.json()


# UPDATED: Generate GPT response with inventory item data
def generate_ai_response(user_query, product_data, requested_info=None):
    info_str = ", ".join(requested_info) if requested_info else "all relevant fields"
    
    prompt = f"""
User asked: "{user_query}"

Product Data:
{product_data}

RESPONSE FORMAT REQUIREMENTS:
1. For numerical values: Provide exact figures with relevant units:
   - Price/Cost: Include currency symbol (e.g., $25.99)
   - Dimensions: Include units (e.g., 750ml, 12.5cm)
   - Percentages: Include % symbol (e.g., 15.5%)
   - Inventory: Include "units" (e.g., 50 units)

2. For categorical data: Reference exact terms or values from the dataset:
   - Product status: Use exact status (e.g., ACTIVE, DRAFT, ARCHIVED)
   - Categories: Use exact category names from productType or tags

3. Missing Data: If a value is absent in the dataset, clearly state "information unavailable" (not "N/A")

4. Error Handling: If data is missing or unavailable for a requested field, indicate this clearly without making assumptions

5. Stick to what is explicitly provided - avoid assumptions where data is incomplete

Field definitions:
- 'price' = customer-facing selling price from variant
- 'cost' = internal cost from inventory item  
- 'profit' = calculated profit (price - cost)
- 'margin' = calculated margin percentage ((profit/price) * 100)
- 'inventory' = stock quantity
- 'image_url' = main product image URL

Respond using only: {info_str}. 

For missing fields, state "unavailable" clearly.
If 'image_url' is requested, return the direct image URL only once without markdown or formatting.
Use factual, precise language with exact values and appropriate units.
"""
    
    response = openai_client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,  # Lower temperature for more consistent formatting
        max_tokens=500
    )
    return response.choices[0].message.content.strip()



# UPDATED: Generate comparison response with inventory item data
def generate_comparison_response(user_query, product1_data, product2_data, requested_info=None):
    info_str = ", ".join(requested_info) if requested_info else "all relevant fields"
    
    # Check if user is asking for specific field comparison
    user_query_lower = user_query.lower()
    
    # More comprehensive keyword detection
    specific_field_patterns = {
        'price': ['price', 'pricing', 'cost to customer', 'selling price', 'prices'],
        'cost': ['cost', 'unit cost', 'internal cost', 'costs'],
        'profit': ['profit', 'profitability', 'profits'],
        'margin': ['margin', 'profit margin', 'percentage', 'margins'],
        'inventory': ['inventory', 'stock', 'quantity', 'quantities'],
        'dimensions': ['dimensions', 'dimension', 'exterior dimensions', 'size', 'measurements']
    }
    
    # Determine if user wants only specific field comparison
    specific_field_requested = None
    
    # Check if the requested_info has only one item and it matches a field
    if requested_info and len(requested_info) == 1:
        single_field = requested_info[0].lower()
        if single_field in specific_field_patterns:
            specific_field_requested = single_field
    
    # Alternative: Check if query contains specific comparison keywords
    if not specific_field_requested:
        for field, patterns in specific_field_patterns.items():
            if any(pattern in user_query_lower for pattern in patterns):
                # Check if this field is in requested_info or if it's the dominant theme
                if not requested_info or field in (requested_info or []):
                    specific_field_requested = field
                    break
    
    # print(f"Specific field requested: {specific_field_requested}")  # Debug print
    # print(f"Requested info: {requested_info}")  # Debug print
    
    # Create more restrictive prompt for specific field requests
    if specific_field_requested:
        # Get the actual values for comparison
        def get_field_value(product_data, field):
            if field == 'price':
                return product_data.get('variant', {}).get('price', 'N/A')
            elif field == 'cost':
                return product_data.get('cost', 'N/A')
            elif field == 'profit':
                return product_data.get('profit', 'N/A')
            elif field == 'margin':
                return product_data.get('margin', 'N/A')
            elif field == 'inventory':
                return product_data.get('variant', {}).get('inventoryQuantity', 'N/A')
            elif field == 'dimensions': 
                return product_data.get('dimensions', 'N/A')
            else:
                return 'N/A'
        
        product1_value = get_field_value(product1_data, specific_field_requested)
        product2_value = get_field_value(product2_data, specific_field_requested)
        
        product1_title = product1_data.get('title', 'Product 1')
        product2_title = product2_data.get('title', 'Product 2')
        
        # Create a focused prompt following strict response format
        prompt = f"""
        User asked: "{user_query}"
        
        Product 1: {product1_title}
        {specific_field_requested.capitalize()}: {product1_value}
        
        Product 2: {product2_title}
        {specific_field_requested.capitalize()}: {product2_value}
        
        RESPONSE FORMAT REQUIREMENTS:
        1. For numerical values: Provide exact figures with relevant units (e.g., price in dollars, dimensions in cm)
        2. For categorical data: Reference exact terms or values from the dataset
        3. Missing Data: If a value is absent, clearly state "unavailable" or "information unavailable"
        4. Error Handling: If data is missing, indicate this clearly without making assumptions
        5. Stick to what is explicitly provided in the data
        
        IMPORTANT: The user is asking ONLY about {specific_field_requested} comparison.
        
        Response format:
        - If both values are available: "{product1_title} {specific_field_requested} is [exact value with units], while {product2_title} {specific_field_requested} is [exact value with units]."
        - If one value is unavailable: "{product1_title} {specific_field_requested} is [value/unavailable], while {product2_title} {specific_field_requested} is [value/unavailable]."
        - If both values are unavailable: "{specific_field_requested.capitalize()} information is unavailable for both products."
        
        For price/cost values: Include currency symbol (e.g., $25.99)
        For percentage values: Include % symbol (e.g., 15.5%)
        For inventory: Include units (e.g., 50 units)
        
        DO NOT mention any other fields. Use only normal text without markdown formatting.
        """
    else:
        # Original prompt for general comparisons with strict format requirements
        prompt = f"""
        User asked: "{user_query}"
        
        Product 1 Data:
        {product1_data}
        
        Product 2 Data:
        {product2_data}
        
        RESPONSE FORMAT REQUIREMENTS:
        1. For numerical values: Provide exact figures with relevant units (e.g., price in dollars, cost in dollars, dimensions in cm)
        2. For categorical data: Reference exact terms or values from the dataset
        3. Missing Data: If a value is absent, clearly state "unavailable" or "information unavailable"
        4. Error Handling: If data is missing, indicate this clearly without making assumptions
        5. Stick to what is explicitly provided in the data
        
        Field definitions:
        - 'price' = customer-facing selling price from variant (include $ symbol)
        - 'cost' = internal cost from inventory item (include $ symbol)
        - 'profit' = calculated profit (price - cost) (include $ symbol)
        - 'margin' = calculated margin percentage ((profit/price) * 100) (include % symbol)
        - 'inventory' = stock quantity (include "units" if applicable)
        
        Compare these two products focusing on: {info_str}. 
        
        For each field:
        - Provide exact values with appropriate units
        - If data is missing, state "unavailable" 
        - Do not make assumptions about missing data
        - Use clear, factual language
        
        Format: Use normal text without special characters, markdown, asterisks, underscores, or formatting symbols.
        """
    
    response = openai_client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,  # Lower temperature for more consistent formatting
        max_tokens=500
    )
    
    return response.choices[0].message.content.strip()



# ENHANCED: Process status and category queries
def process_status_and_category_query(intent, user_input):
    """Process queries about product status and/or category with strict response format"""
    
    status_value = intent.get("status_value")
    category_value = intent.get("category_value")
    query_type = intent.get("query_type", "list")
    
    # print(f"Processing query with status: {status_value}, category: {category_value}")  # Debug print
    
    # Search products based on criteria
    results = search_products_by_criteria(status=status_value, category=category_value)
    products = results.get("data", {}).get("products", {}).get("edges", [])
    
    # Additional client-side filtering for better category matching
    if category_value and products:
        filtered_products = []
        for product in products:
            node = product["node"]
            product_type = node.get("productType", "").lower()
            tags = [tag.lower() for tag in node.get("tags", [])]
            
            # Check if category matches productType or any tag
            if (category_value.lower() in product_type or 
                category_value.lower() in tags or
                any(category_value.lower() in tag for tag in tags)):
                filtered_products.append(product)
        
        products = filtered_products
    
    # Handle missing data according to strict format requirements
    if not products:
        criteria_text = []
        if status_value:
            criteria_text.append(f"status '{status_value}'")
        if category_value:
            criteria_text.append(f"category '{category_value}'")
        
        criteria_display = " and ".join(criteria_text) if criteria_text else "specified criteria"
        return f"No products found with {criteria_display}. Please verify the criteria or try different search terms."
    
    # Format response based on query type with exact values
    if query_type == "count":
        criteria_text = []
        if status_value:
            criteria_text.append(f"status '{status_value}'")
        if category_value:
            criteria_text.append(f"category '{category_value}'")
        
        criteria_display = " and ".join(criteria_text) if criteria_text else "specified criteria"
        return f"Found {len(products)} products with {criteria_display}."
    
    elif query_type == "list":
        criteria_text = []
        if status_value:
            criteria_text.append(f"status '{status_value}'")
        if category_value:
            criteria_text.append(f"category '{category_value}'")
        
        criteria_display = " and ".join(criteria_text) if criteria_text else "specified criteria"
        
        if len(products) <= 15:
            product_list = []
            for product in products:
                node = product["node"]
                product_type = node.get("productType", "unavailable")
                status = node.get("status", "unavailable")
                product_list.append(f"• {node['title']} (Status: {status}, Type: {product_type})")
            return f"Products with {criteria_display}:\n" + "\n".join(product_list)
        else:
            # Show first 15 and mention total count
            product_list = []
            for product in products[:15]:
                node = product["node"]
                product_type = node.get("productType", "unavailable")
                status = node.get("status", "unavailable")
                product_list.append(f"• {node['title']} (Status: {status}, Type: {product_type})")
            return f"Showing first 15 of {len(products)} products with {criteria_display}:\n" + "\n".join(product_list)
    
    else:  # Default to list format
        product_list = []
        for product in products:
            node = product["node"]
            product_type = node.get("productType", "unavailable")
            status = node.get("status", "unavailable")
            product_list.append(f"• {node['title']} (Status: {status}, Type: {product_type})")
        
        criteria_text = []
        if status_value:
            criteria_text.append(f"status '{status_value}'")
        if category_value:
            criteria_text.append(f"category '{category_value}'")
        
        criteria_display = " and ".join(criteria_text) if criteria_text else "specified criteria"
        
        return f"Products with {criteria_display}:\n" + "\n".join(product_list)


def process_date_query(intent, user_input):
    """Process queries about products created on specific dates"""
    
    date_condition = intent.get("date_condition")
    date_value = intent.get("date_value")
    query_type = intent.get("query_type", "list")
    
    # print(f"Processing date query with condition: {date_condition}, date: {date_value}")  # Debug print
    
    # Search products based on date criteria
    results = search_products_by_date(date_condition, date_value)
    products = results.get("data", {}).get("products", {}).get("edges", [])
    
    if not products:
        return f"No products found created {date_condition} {date_value}."
    
    # Format response based on query type
    if query_type == "count":
        return f"Found {len(products)} products created {date_condition} {date_value}."
    
    elif query_type == "list":
        if len(products) <= 15:
            product_list = []
            for product in products:
                node = product["node"]
                created_date = node.get("createdAt", "N/A")[:10]  # Get just the date part
                product_type = node.get("productType", "N/A")
                product_list.append(f"• {node['title']} (Created: {created_date}, Type: {product_type})")
            return f"Products created {date_condition} {date_value}:\n" + "\n".join(product_list)
        else:
            # Show first 15 and mention total count
            product_list = []
            for product in products[:15]:
                node = product["node"]
                created_date = node.get("createdAt", "N/A")[:10]  # Get just the date part
                product_type = node.get("productType", "N/A")
                product_list.append(f"• {node['title']} (Created: {created_date}, Type: {product_type})")
            return f"Showing first 15 of {len(products)} products created {date_condition} {date_value}:\n" + "\n".join(product_list)
    
    else:  # Default to list format
        product_list = []
        for product in products:
            node = product["node"]
            created_date = node.get("createdAt", "N/A")[:10]  # Get just the date part
            product_type = node.get("productType", "N/A")
            product_list.append(f"• {node['title']} (Created: {created_date}, Type: {product_type})")
        
        return f"Products created {date_condition} {date_value}:\n" + "\n".join(product_list)


# UPDATED: Process single product with inventory item data
def process_single_product(product_name_or_sku, requested_info, user_input):
    results = search_products(product_name_or_sku)
    products = results.get("data", {}).get("products", {}).get("edges", [])

    if not products:
        return "No product matched your query."
    elif len(products) > 1:
        titles = [p["node"]["title"] for p in products]
        st.session_state.awaiting_clarification = True
        st.session_state.clarification_type = "product"
        st.session_state.clarification_data = products
        return f"I found multiple products. Which one? Options: {', '.join(titles)}"
    else:
        product = products[0]["node"]
        gid = product["id"]
        details = fetch_product_details_by_gid(gid)
        product_info = details["data"]["product"]

        variants = product_info.get("variants", {}).get("edges", [])
        if len(variants) > 1:
            st.session_state.awaiting_clarification = True
            st.session_state.clarification_type = "variant"
            st.session_state.clarification_data = variants
            st.session_state.original_product = product_info
            return "This product has multiple variants. Which one are you referring to?"
        else:
            variant = variants[0]["node"] if variants else {}
            
            # Extract cost from inventory item
            cost = "N/A"
            if variant.get("inventoryItem") and variant["inventoryItem"].get("unitCost"):
                cost = variant["inventoryItem"]["unitCost"]["amount"]
            
            # Calculate profit and margin
            price = variant.get("price", "N/A")
            profit_margin_data = calculate_profit_and_margin(cost, price)
            
            images = product_info.get("images", {}).get("edges", [])
            image_url = images[0]["node"]["url"] if images else "N/A"

            # Prepare enhanced product data
            enhanced_product_data = {
                "title": product_info.get("title"),
                "variant": variant,
                "cost": cost,
                "profit": profit_margin_data["profit"],
                "margin": profit_margin_data["margin"],
                "image_url": image_url
            }

            answer = generate_ai_response(user_input, enhanced_product_data, requested_info)
            return answer


# UPDATED: Process comparison with inventory item data
def process_comparison(product1_name, product2_name, requested_info, user_input):
    # print(f"Searching for product1: {product1_name}")  # Debug print
    # print(f"Searching for product2: {product2_name}")  # Debug print
    
    # Search for first product
    results1 = search_products(product1_name)
    products1 = results1.get("data", {}).get("products", {}).get("edges", [])
    # print(f"Products1 found: {len(products1)}")  # Debug print
    
    # Search for second product
    results2 = search_products(product2_name)
    products2 = results2.get("data", {}).get("products", {}).get("edges", [])
    # print(f"Products2 found: {len(products2)}")  # Debug print

    if not products1:
        return f"No product found for '{product1_name}'. Please check the spelling or try a different search term."
    if not products2:
        return f"No product found for '{product2_name}'. Please check the spelling or try a different search term."

    # Get first product from each search (taking the first match)
    product1 = products1[0]["node"]
    product2 = products2[0]["node"]
    
    # print(f"Product1: {product1['title']}")  # Debug print
    # print(f"Product2: {product2['title']}")  # Debug print
    
    # Fetch details for both products
    details1 = fetch_product_details_by_gid(product1["id"])
    details2 = fetch_product_details_by_gid(product2["id"])
    
    product1_info = details1["data"]["product"]
    product2_info = details2["data"]["product"]

    # Helper function to extract cost, profit, and margin
    def extract_financial_data(product_info):
        variants = product_info.get("variants", {}).get("edges", [])
        variant = variants[0]["node"] if variants else {}
        
        # Extract cost from inventory item
        cost = "N/A"
        if variant.get("inventoryItem") and variant["inventoryItem"].get("unitCost"):
            cost = variant["inventoryItem"]["unitCost"]["amount"]
        
        # Calculate profit and margin
        price = variant.get("price", "N/A")
        profit_margin_data = calculate_profit_and_margin(cost, price)
        
        return {
            "title": product_info.get("title"),
            "variant": variant,
            "cost": cost,
            "profit": profit_margin_data["profit"],
            "margin": profit_margin_data["margin"]
        }

    # Get financial data for both products
    product1_data = extract_financial_data(product1_info)
    product2_data = extract_financial_data(product2_info)

    # Generate comparison response
    answer = generate_comparison_response(user_input, product1_data, product2_data, requested_info)
    return answer


# ENHANCED: Enhanced input handler with status and category query support
def handle_user_input(user_input):
    """Enhanced input handler with date, status and category query support"""
    
    # Check for date-based queries first
    date_intent = extract_date_intent(user_input)
    if date_intent:
        # print(f"Date intent detected: {date_intent}")  # Debug print
        answer = process_date_query(date_intent, user_input)
        return answer
    
    # Check for status and/or category-based queries
    status_category_intent = extract_status_and_category_intent(user_input)
    # print(f"Status/Category intent detected: {status_category_intent}")  # Debug print
    
    if (status_category_intent and 
        (status_category_intent.get("is_status_query", False) or 
         status_category_intent.get("is_category_query", False))):
        
        # print(f"Processing status/category query")  # Debug print
        answer = process_status_and_category_query(status_category_intent, user_input)
        return answer
    
    # Check for comparison queries
    comparison_intent = extract_comparison_intent(user_input)
    
    # Fallback: Check for comparison patterns manually
    is_comparison_manual = False
    if not (comparison_intent and comparison_intent.get("is_comparison", False)):
        comparison_words = ["compare", "vs", "versus", "difference between", "and"]
        user_lower = user_input.lower()
        if any(word in user_lower for word in comparison_words):
            # Simple regex to extract two product identifiers
            pattern = r'(\w+[-\w]*)\s+(?:and|vs|versus)\s+(\w+[-\w]*)'
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                is_comparison_manual = True
                comparison_intent = {
                    "is_comparison": True,
                    "product1_name_or_sku": match.group(1),
                    "product2_name_or_sku": match.group(2),
                    "requested_info": ["price", "cost", "profit", "margin"] if any(word in user_lower for word in ["cost", "profit", "margin"]) else ["price", "cost", "inventory"]
                }
    
    if (comparison_intent and comparison_intent.get("is_comparison", False)) or is_comparison_manual:
        # Handle comparison
        answer = process_comparison(
            comparison_intent["product1_name_or_sku"],
            comparison_intent["product2_name_or_sku"],
            comparison_intent["requested_info"],
            user_input
        )
        return answer
    else:
        # Handle single product query (existing functionality)
        intent = extract_product_intent(user_input)
        if not intent:
            return "Sorry, I couldn't understand your question."
        else:
            answer = process_single_product(
                intent["product_name_or_sku"],
                intent["requested_info"],
                user_input
            )
            return answer


# Streamlit UI
st.title("🛍️ Conversational Shopify Chatbot")
user_input = st.chat_input("Ask about a product...")

if user_input:
    st.session_state.conversation.append(("user", user_input))

    # If awaiting clarification on variant, check the variant details
    if st.session_state.awaiting_clarification and st.session_state.clarification_type == "variant":
        variants = st.session_state.clarification_data
        result = extract_variant_intent(user_input, variants)

        if result["matched_variant_title"]:
            # Retrieve the selected variant
            selected_variant = next(
                v["node"] for v in variants if v["node"]["title"] == result["matched_variant_title"]
            )
            product = st.session_state.original_product
            
            # Extract cost from inventory item
            cost = "N/A"
            if selected_variant.get("inventoryItem") and selected_variant["inventoryItem"].get("unitCost"):
                cost = selected_variant["inventoryItem"]["unitCost"]["amount"]
            
            # Calculate profit and margin
            price = selected_variant.get("price", "N/A")
            profit_margin_data = calculate_profit_and_margin(cost, price)
            
            images = product.get("images", {}).get("edges", [])
            image_url = images[0]["node"]["url"] if images else "N/A"
            
            # Prepare enhanced product data
            enhanced_product_data = {
                "title": product.get("title"),
                "variant": selected_variant,
                "cost": cost,
                "profit": profit_margin_data["profit"],
                "margin": profit_margin_data["margin"],
                "image_url": image_url
            }
            
            answer = generate_ai_response(user_input, enhanced_product_data, result["requested_info"])
            st.session_state.conversation.append(("bot", answer))
            st.session_state.awaiting_clarification = False  # Clarification is done
            st.session_state.clarified_variant = selected_variant  # Store clarified variant

        else:
            st.session_state.conversation.append(("bot", "I couldn't match that to any variant. Please try again."))

    # Handle first query where no clarification is needed
    else:
        st.session_state.original_query = user_input
        
        # Use the new enhanced handler
        answer = handle_user_input(user_input)
        st.session_state.conversation.append(("bot", answer))

# Display chat
for role, message in st.session_state.conversation:
    if role == "bot":
        st.chat_message(role).text(message)  # Use .text() instead of .write()
    else:
        st.chat_message(role).write(message)
