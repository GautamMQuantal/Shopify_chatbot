#Currently working - Improved Good Deployed 22nd August 2025

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
    "clarification_data", "original_query", "original_product", "clarified_variant", "original_requested_info","current_product_memory", "current_product_data"
]:
     if key not in st.session_state:
        if "conversation" in key or "clarification_data" in key:
            st.session_state[key] = []
        elif "awaiting" in key:
            st.session_state[key] = False
        elif key in ["current_product_memory", "current_product_data"]:  # NEW
            st.session_state[key] = None  # NEW: Initialize memory as None
        else:
            st.session_state[key] = ""

# NEW: Check if input is product-related
def is_product_related_query(query):
    """Check if the query is actually asking about a product"""
    
    # Convert to lowercase for checking
    query_lower = query.lower().strip()
    
    # Common greetings and non-product queries
    non_product_patterns = [
        r'^(hi|hii|hello|hey|good morning|good afternoon|good evening)$',
        r'^(how are you|what\'s up|how\'s it going)$',
        r'^(thanks|thank you|bye|goodbye|exit|quit)$',
        r'^(help|what can you do|what do you do)$',
        r'^(test|testing)$'
    ]
    
    # Check if it matches non-product patterns
    for pattern in non_product_patterns:
        if re.match(pattern, query_lower):
            return False
    
    # Product-related keywords that indicate a product query
    product_keywords = [
        'price', 'cost', 'inventory', 'stock', 'dimensions', 'profit', 'margin', 'markup',
        'product', 'item', 'sku', 'part number', 'p/n', 'compare', 'vs', 'versus',
        'show me', 'tell me about', 'find', 'search', 'looking for',
        'how much', 'what is the', 'give me', 'i need', 'i want',
        'weight', 'wheels', 'total products', 'how many products', 'count',
        'part', 'number', 'model', 'formula'
    ]
    
    # Status/category related keywords
    status_keywords = ['draft', 'active', 'archived', 'published', 'unpublished', 'status']
    category_keywords = ['category', 'categorized', 'type', 'product type']
    date_keywords = ['created after', 'created before', 'created on', 'after', 'before', 'since']
    
    all_keywords = product_keywords + status_keywords + category_keywords + date_keywords
    
    # Check if query contains product-related keywords
    if any(keyword in query_lower for keyword in all_keywords):
        return True
    
    # Check if query looks like it contains a product name or SKU
    if re.search(r'\b[A-Z0-9]{2,}[-A-Z0-9]*\b', query.upper()):
        return True
    
    # If query is longer than 3 words and doesn't match non-product patterns, 
    # it might be a product query
    if len(query.split()) > 3:
        return True
    
    return False

def generate_general_response(query):
    """Generate a general chatbot response for non-product queries"""
    
    query_lower = query.lower().strip()
    
    # Predefined responses for common queries
    responses = {
        'hi': "Hello! I'm your Shopify product assistant. I can help you find information about products, compare items, check inventory, and more. What product would you like to know about?",
        'hello': "Hi there! I'm here to help you with product information. You can ask me about prices, inventory, costs, profits, margins, or compare different products. What can I help you find?",
        'hey': "Hey! I'm your product assistant. I can help you search for products, check their details, compare items, or find products by category or status. What are you looking for?",
        'help': "I'm your Shopify product assistant! Here's what I can do:\n\n📦 **Product Information**: Ask about price, cost, inventory, dimensions, profit, margin\n🔍 **Product Search**: Search by name, SKU, or part number\n⚖️ **Compare Products**: Compare two products side by side\n📊 **Filter Products**: Find products by status (draft/active/archived) or category\n📅 **Date Queries**: Find products created before/after specific dates\n\nTry asking: 'What is the price of [product name]?' or 'Compare [product A] and [product B]'",
        'thanks': "You're welcome! Feel free to ask about any other products.",
        'bye': "Goodbye! Feel free to come back anytime you need product information."
    }
    
    # Check for exact matches first
    if query_lower in responses:
        return responses[query_lower]
    
    # Check for partial matches
    if 'how are you' in query_lower or "what's up" in query_lower:
        return "I'm doing great and ready to help! I specialize in providing product information from your Shopify store. What would you like to know?"
    elif 'what can you do' in query_lower or 'what do you do' in query_lower:
        return responses['help']
    elif any(word in query_lower for word in ['thanks', 'thank you']):
        return responses['thanks']
    elif any(word in query_lower for word in ['bye', 'goodbye', 'see you']):
        return responses['bye']
    elif 'help' in query_lower:
        return responses['help']
    
    # Default response for unclear queries
    return "I'm here to help you with product information! You can ask me about:\n• Product prices, costs, and inventory\n• Profit and margin calculations\n• Product comparisons\n• Finding products by category or status\n\nWhat product would you like to know about?"

# NEW: Check if input is asking for details about the current product
def is_asking_about_current_product(query):
    """Check if the query is asking for more details about the currently remembered product"""
    
    query_lower = query.lower().strip()
    
    # Keywords that indicate asking for product details without specifying a product
    current_product_indicators = [
        # Pronouns referring to current product
        r'\bit\b', r'\bthis\b', r'\bthat\b', r'\bthe product\b',
        
        # Direct questions about product attributes - ENHANCED
        r'\bwhat\s+is\s+the\s+(price|cost|profit|margin|markup|inventory|dimensions?|weight|part\s+number|sku)\b',
        r'\bwhat\s+(price|cost|profit|margin|markup|inventory|dimensions?|weight|part\s+number|sku)\b',
        r'\b(price|cost|profit|margin|markup|inventory|dimensions?|weight|part\s+number|sku)\s*\?\s*$',
        r'^\s*(price|cost|profit|margin|markup|inventory|dimensions?|weight|part\s+number|sku)\s*$',
        
        # More flexible question patterns - ENHANCED
        r'\b(what|whats|tell|show|give|provide).*\b(price|cost|profit|margin|markup|inventory|dimensions?|map|MAP|url|image|weight|part\s+number|sku)\b',
        r'\bhow much\b',
        r'\bwhat does it cost\b',
        
        # Image/URL specific patterns
        r'url image', r'image url', r'url of.*image', r'image.*url',
        r'^url$', r'^image$', r'^picture$', r'^photo$',
        
        # Selling/selling price questions
        r'sell price', r'selling price', r'sale price', r'advertised price', r'retail price',
        
        # More details requests
        r'more details', r'other details', r'additional info', r'more info',
    ]
    
    # Check if any pattern matches
    for pattern in current_product_indicators:
        if re.search(pattern, query_lower):
            return True
    
    return False


# NEW: Extract information request from current product query
def extract_current_product_info_request(query):
    """Extract what information the user wants about the current product"""
    
    query_lower = query.lower()
    
    # Map query patterns to requested info - ENHANCED
    info_mapping = {
        'price': ['price', 'sell price', 'selling price', 'sale price', 'cost to customer', 'map', 'MAP', 'advertised price', 'retail price'],
        'cost': ['cost', 'unit cost', 'internal cost', 'how much does it cost'],
        'profit': ['profit', 'profitability'],
        'margin': ['margin', 'profit margin', 'percentage margin'],
        'markup': ['markup', 'mark up', 'mark-up'],
        'inventory': ['inventory', 'stock', 'quantity', 'how many','quantities'],
        'dimensions': ['dimensions', 'dimension', 'size', 'measurements'], 
        'image_url': ['image', 'picture', 'photo', 'show me', 'url image', 'image url', 'url of image', 'image of url', 'url'],
        'cost_update': ['cost updated', 'cost last updated', 'last cost update', 'when cost updated', 'cost update time'],
        'weight': ['weight', 'how heavy', 'mass', 'weighs', 'heavy', 'weigh','weights'],
        'wheels': ['wheels', 'wheel', 'rolling', 'roll', 'portable', 'wheeled'],
        'part_number': ['part number', 'p/n', 'sku', 'model number', 'product number', 'item number']

    }
    
    requested_info = []
    
    # Check for specific information requests
    # Check for specific information requests - ENHANCED
    for info_type, keywords in info_mapping.items():
        if any(keyword.lower() in query_lower for keyword in keywords):
            requested_info.append(info_type)

    # Additional keyword-based detection
    if any(word in query_lower for word in ['price', 'cost', 'profit', 'margin', 'markup', 'inventory', 'dimensions', 'image', 'url']):
        # Extract based on keywords found
        if 'price' in query_lower and 'price' not in requested_info:
            requested_info.append('price')
        if 'cost' in query_lower and 'cost' not in requested_info:
            requested_info.append('cost')
        if 'dimensions' in query_lower and 'dimensions' not in requested_info:
            requested_info.append('dimensions')
        if any(word in query_lower for word in ['inventory', 'stock', 'quantity']) and 'inventory' not in requested_info:
            requested_info.append('inventory')
        if any(word in query_lower for word in ['image', 'picture', 'photo', 'url']) and 'image_url' not in requested_info:
            requested_info.append('image_url')
    
    # Additional specific checks for tricky patterns - NEW
    if any(pattern in query_lower for pattern in ['url image', 'image url', 'provide me the url', 'what is the url']):
        if 'image_url' not in requested_info:
            requested_info.append('image_url')

    if re.search(r'\bwhat\s+is\s+the\s+weight\b', query_lower) and 'weight' not in requested_info:
        requested_info.append('weight')
    
    if re.search(r'\bwhat.*part\s+number\b', query_lower) and 'part_number' not in requested_info:
        requested_info.append('part_number')
        
    if re.search(r'\bwhat.*sku\b', query_lower) and 'part_number' not in requested_info:
        requested_info.append('part_number')
    
    # Default to general info if nothing specific found
    if not requested_info:
        if any(word in query_lower for word in ['details', 'info', 'information', 'tell me', 'show me']):
            requested_info = ['price', 'cost', 'inventory', 'profit', 'margin']
        else:
            requested_info = ['price']  # Default to price for simple queries
    
    return requested_info


# NEW: Store product in memory
def store_product_in_memory(product_title, product_data):
    """Store the current product and its data in session memory"""
    st.session_state.current_product_memory = product_title
    st.session_state.current_product_data = product_data


# NEW: Clear product memory
def clear_product_memory():
    """Clear the current product memory"""
    st.session_state.current_product_memory = None
    st.session_state.current_product_data = None


# NEW: Check if a new product is being requested
def is_new_product_request(query):
    """Check if the user is asking about a new/different product"""
    
    # If no current product in memory, any product query is new
    if not st.session_state.current_product_memory:
        return True
    
    current_product = st.session_state.current_product_memory.lower()
    query_lower = query.lower()
    
    # Extract potential product names/SKUs from the query
    intent = extract_product_intent(query)
    if intent and intent.get("product_name_or_sku"):
        requested_product = intent["product_name_or_sku"].lower()
        
        # Check if the requested product is different from current
        if requested_product not in current_product and current_product not in requested_product:
            return True
    
    # Check for comparison queries (always considered new request)
    comparison_intent = extract_comparison_intent(query)
    if comparison_intent and comparison_intent.get("is_comparison", False):
        return True
    
    return False



# Extract product intent
def extract_product_intent(query):
    prompt = f"""
From the query below, extract:
1. product_name_or_sku (string) - can be SKU, part number, P/N, or product title keywords
2. requested_info (list of fields like price, cost, inventory, dimensions, profit, margin, markup)

Note: SKU can also be referred to as "part number" or "P/N"

IMPORTANT: Only extract if this is clearly a product-related query. If the query is a greeting, general question, or doesn't mention any specific product, return null.

Respond as JSON:
{{"product_name_or_sku": "...", "requested_info": ["...", "..."]}}

If this is not a product query, respond with:
{{"product_name_or_sku": null, "requested_info": []}}

Query: "{query}"
"""
    response = openai_client.chat.completions.create(
        model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=300
    )
    try:
        result = eval(response.choices[0].message.content.strip())
        # Additional validation
        if result.get("product_name_or_sku") is None or result.get("product_name_or_sku") == "":
            return None
        return result
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
        model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=300
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
                model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=200
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
            model="gpt-3.5-turbo", 
            messages=[{"role": "user", "content": prompt}], 
            temperature=0, 
            max_tokens=200
        )
        result = eval(response.choices[0].message.content.strip())
        return result
    except:
        return None
    

def extract_cost_update_intent(query):
    """Simple function to check if the query is asking about cost updates"""
    query_lower = query.lower().strip()
    
    # More specific patterns for cost update queries
    cost_update_patterns = [
        r'cost.*updated',
        r'cost.*changed',
        r'cost.*modified',
        r'updated.*cost',
        r'changed.*cost',
        r'modified.*cost',
        r'when.*cost.*updated',
        r'when.*updated.*cost',
        r'last.*cost.*update',
        r'cost.*last.*updated'
    ]
    
    # Check if query matches any cost update pattern
    return any(re.search(pattern, query_lower) for pattern in cost_update_patterns)

def extract_cost_update_product_name(query):
    """Simple function to extract product name from cost update query"""
    query_lower = query.lower()
    
    # Check if this is a general cost update query (no specific product mentioned)
    general_patterns = [
        r'^when was.*cost.*updated',
        r'^when was.*last.*cost',
        r'^when.*last.*cost.*updated',
        r'^when.*cost.*last.*updated',
        r'when was the last time.*cost.*updated',
        r'when did.*cost.*get updated'
    ]
    
    # If it matches a general pattern, return None (asking about current product)
    for pattern in general_patterns:
        if re.search(pattern, query_lower):
            return None
    
    # Remove common cost update related words to isolate product name
    remove_words = ['cost', 'costs', 'updated', 'changed', 'modified', 'update', 'change', 'modification', 
                   'when', 'was', 'the', 'last', 'of', 'for', 'time', 'date', 'product', 'item',
                   'we', 'had', 'did', 'get', 'have']  # Added more stop words
    
    # Split query and remove update-related words
    words = query.split()
    product_words = []
    
    for word in words:
        word_clean = word.lower().strip('.,!?')
        if word_clean not in remove_words and len(word_clean) > 1:
            product_words.append(word)
    
    if product_words:
        product_name = ' '.join(product_words).strip()
        # Remove quotes if present
        product_name = product_name.strip('"\'')
        return product_name if product_name else None
    
    return None


def extract_weight_from_variant(variant):
    """Extract weight information from variant with correct GraphQL structure"""
    try:
        inventory_item = variant.get("inventoryItem", {})
        measurement = inventory_item.get("measurement", {})
        weight_data = measurement.get("weight", {})
        
        if weight_data:
            weight_value = weight_data.get("value")
            weight_unit = weight_data.get("unit", "")
            
            if weight_value is not None and weight_value != 0:
                return f"{weight_value} {weight_unit}" if weight_unit else f"{weight_value}"
            else:
                return "information unavailable"
        else:
            return "information unavailable"
            
    except (KeyError, TypeError, AttributeError):
        return "information unavailable"



def get_total_product_count():
    """Get total count of products on the site with pagination"""
    total_count = 0
    has_next = True
    cursor = None

    while has_next:
        query = f"""
        {{
          products(first: 250{', after: "' + cursor + '"' if cursor else ''}) {{
            edges {{
              cursor
              node {{ id }}
            }}
            pageInfo {{
              hasNextPage
              endCursor
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
        total_count += len(products)
        page_info = result.get("data", {}).get("products", {}).get("pageInfo", {})
        has_next = page_info.get("hasNextPage", False)
        cursor = page_info.get("endCursor")
    
    return f"{total_count} products"



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

def get_inventory_item_cost_update_time(inventory_item_id):
    """
    Fetch the cost update timestamp from inventory item
    Note: Shopify doesn't track cost-specific update times, so we get the general update time
    """
    query = f"""
    {{
      inventoryItem(id: "{inventory_item_id}") {{
        id
        updatedAt
        unitCost {{
          amount
          currencyCode
        }}
        tracked
        sku
      }}
    }}
    """
    
    try:
        response = requests.post(
            f"https://{SHOPIFY_STORE_URL}/admin/api/2023-07/graphql.json",
            headers=headers,
            json={"query": query}
        )
        
        result = response.json()
        inventory_item = result.get("data", {}).get("inventoryItem", {})
        
        return {
            "updated_at": inventory_item.get("updatedAt", "N/A"),
            "cost": inventory_item.get("unitCost", {}).get("amount", "N/A") if inventory_item.get("unitCost") else "N/A",
            "currency": inventory_item.get("unitCost", {}).get("currencyCode", "USD") if inventory_item.get("unitCost") else "USD"
        }
    except Exception as e:
        print(f"Error fetching inventory item details: {e}")
        return {"updated_at": "N/A", "cost": "N/A", "currency": "USD"}


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


def calculate_markup(cost, price):
    """Calculate markup from cost and price (Price / Cost)"""
    try:
        cost_float = float(cost) if cost and cost != "N/A" else 0
        price_float = float(price) if price and price != "N/A" else 0
        
        if cost_float == 0:
            return {"markup": "N/A"}
        
        markup = price_float / cost_float
        
        return {"markup": f"{markup:.2f}"}
    except (ValueError, TypeError, ZeroDivisionError):
        return {"markup": "N/A"}


def detect_wheels_in_product(product_info):
    """Detect if product has wheels based on description and tags"""
    
    # Check product description
    description = product_info.get("description", "").lower()
    
    # Check product tags
    tags = [tag.lower() for tag in product_info.get("tags", [])]
    
    # Check product title
    title = product_info.get("title", "").lower()
    
    # Wheel indicators
    wheel_keywords = [
        'wheel', 'wheels', 'wheeled', 'rolling', 'rollable', 'portable',
        'mobility', 'mobile', 'transport', 'trolley', 'cart'
    ]
    
    # Check in all text fields
    all_text = f"{description} {' '.join(tags)} {title}"
    
    has_wheels = any(keyword in all_text for keyword in wheel_keywords)
    
    return "Yes" if has_wheels else "No clear indication"


def process_cost_update_query(query, product_name_or_sku=None):
    """Enhanced function to process cost update timestamp queries"""
    
    # If no product specified, check if we have a current product in memory
    if not product_name_or_sku and st.session_state.current_product_memory:
        # User is asking about current product
        current_data = st.session_state.current_product_data
        if current_data and 'title' in current_data:
            # Get the variant data to access inventory item ID
            variant_data = current_data.get('variant', {})
            inventory_item = variant_data.get('inventoryItem', {})
            inventory_item_id = inventory_item.get('id')
            
            if inventory_item_id:
                # Get cost update information from inventory item
                cost_update_info = get_inventory_item_cost_update_time(inventory_item_id)
                updated_at = cost_update_info.get("updated_at", "N/A")
                current_cost = cost_update_info.get("cost", "N/A")
                currency = cost_update_info.get("currency", "USD")
                
                product_title = current_data.get('title', 'Current Product')
                
                if updated_at != "N/A":
                    # Format the timestamp to be more readable
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                        formatted_date = dt.strftime("%B %d, %Y at %I:%M %p UTC")
                        
                        cost_display = f"${current_cost}" if current_cost != "N/A" else "unavailable"
                        
                        return f"The cost information for '{product_title}' was last updated on {formatted_date}. Current cost: {cost_display}. Note: This reflects the inventory item's last modification time."
                    except:
                        cost_display = f"${current_cost}" if current_cost != "N/A" else "unavailable"
                        return f"The cost information for '{product_title}' was last updated at {updated_at}. Current cost: {cost_display}."
                else:
                    return f"Cost update information is not available for '{product_title}'."
            else:
                # Fallback to product-level update time
                return f"Detailed cost update information is not available for '{current_data.get('title', 'current product')}'. The product may not have inventory tracking enabled."
        else:
            return "No current product in memory to check cost update information."
    
    # If product name is specified, search for it
    elif product_name_or_sku:
        results = search_products(product_name_or_sku)
        products = results.get("data", {}).get("products", {}).get("edges", [])
        
        if not products:
            return f"No product found matching '{product_name_or_sku}' to check cost update information."
        elif len(products) > 1:
            # Multiple products found - ask for clarification
            st.session_state.awaiting_clarification = True
            st.session_state.clarification_type = "cost_update_product_selection"
            st.session_state.clarification_data = products
            st.session_state.original_query = query
            
            product_list = []
            for i, product in enumerate(products[:5]):  # Show first 5
                product_list.append(f"• {product['node']['title']}")
            
            return f"I found multiple products matching your search:\n" + "\n".join(product_list) + "\n\nCould you please specify which product you're asking about?"
        else:
            # Single product found
            product = products[0]["node"]
            gid = product["id"]
            details = fetch_product_details_by_gid(gid)
            product_info = details["data"]["product"]
            
            # Get the first variant to access inventory item
            variants = product_info.get("variants", {}).get("edges", [])
            if variants:
                variant = variants[0]["node"]
                inventory_item = variant.get("inventoryItem", {})
                inventory_item_id = inventory_item.get("id")
                
                if inventory_item_id:
                    # Get cost update information from inventory item
                    cost_update_info = get_inventory_item_cost_update_time(inventory_item_id)
                    updated_at = cost_update_info.get("updated_at", "N/A")
                    current_cost = cost_update_info.get("cost", "N/A")
                    currency = cost_update_info.get("currency", "USD")
                    
                    product_title = product_info.get("title", "Unknown Product")
                    
                    if updated_at != "N/A":
                        try:
                            from datetime import datetime
                            dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                            formatted_date = dt.strftime("%B %d, %Y at %I:%M %p UTC")
                            
                            cost_display = f"${current_cost}" if current_cost != "N/A" else "unavailable"
                            
                            return f"The cost information for '{product_title}' was last updated on {formatted_date}. Current cost: {cost_display}. Note: This reflects the inventory item's last modification time."
                        except:
                            cost_display = f"${current_cost}" if current_cost != "N/A" else "unavailable"
                            return f"The cost information for '{product_title}' was last updated at {updated_at}. Current cost: {cost_display}."
                    else:
                        return f"Cost update information is not available for '{product_title}'."
                else:
                    # Fallback to product-level update time
                    product_updated_at = product_info.get("updatedAt", "N/A")
                    product_title = product_info.get("title", "Unknown Product")
                    
                    if product_updated_at != "N/A":
                        try:
                            from datetime import datetime
                            dt = datetime.fromisoformat(product_updated_at.replace('Z', '+00:00'))
                            formatted_date = dt.strftime("%B %d, %Y at %I:%M %p UTC")
                            return f"'{product_title}' was last updated on {formatted_date}. Note: Specific cost update tracking is not available for this product."
                        except:
                            return f"'{product_title}' was last updated at {product_updated_at}. Note: Specific cost update tracking is not available."
                    else:
                        return f"Update information is not available for '{product_title}'."
            else:
                return f"No variant information available for '{product_info.get('title', 'the product')}' to check cost updates."
    
    else:
        return "Please specify which product you'd like to check the cost update information for."

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
        model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=300
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
                measurement {{
                  weight {{
                    value
                    unit
                  }}
                }}
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

# UPDATED: Generate GPT response with inventory item data and new fields
def generate_ai_response(user_query, product_data, requested_info=None):
    info_str = ", ".join(requested_info) if requested_info else "all relevant fields"
    
    # Extract variant data
    variant = product_data.get("variant", {})
    
    # Extract weight information
    weight_display = extract_weight_from_variant(variant)
    
    # Extract wheels information from product data
    wheels_info = "information unavailable"
    if "full_product_info" in product_data:
        wheels_info = detect_wheels_in_product(product_data["full_product_info"])
    else:
        title_text = f"{product_data.get('title', '')} {variant.get('title', '')}".lower()
        wheel_keywords = ['wheel', 'wheels', 'wheeled', 'rolling', 'portable', 'mobility', 'mobile']
        if any(keyword in title_text for keyword in wheel_keywords):
            wheels_info = "Yes"
        elif title_text.strip():
            wheels_info = "No clear indication"
    
    # Extract part number (SKU)
    part_number = variant.get('sku', 'information unavailable')
    
    # Check if user is asking specifically for margin
    user_lower = user_query.lower()
    
    # NEW: Check if asking about margin specifically
    is_margin_request = any(word in user_lower for word in ['margin', 'profit margin']) and requested_info and 'margin' in requested_info
    
    # Check if user is asking specifically for margin formula
    margin_formula_patterns = [
        r'margin.*formula',
        r'how.*calculate.*margin',
        r'margin.*calculation',
        r'formula.*margin',
        r'calculate.*margin'
    ]
    
    is_margin_formula_request = any(re.search(pattern, user_lower) for pattern in margin_formula_patterns)

    prompt = f"""
User asked: "{user_query}"

Product Data:
{product_data}

Additional Information:
- Weight: {weight_display}
- Has Wheels: {wheels_info}
- Part Number/SKU: {part_number}

SPECIAL INSTRUCTIONS:
{"1. MARGIN CALCULATION: The user is asking about margin. Provide the margin value AND show the calculation. Extract the actual price and cost values from the product data and show: 'Margin: X% (calculated as: (($Y - $Z) / $Y) × 100 = X%)' where Y is the price and Z is the cost. The formula should be explicitly included as part of the response if it's a margin request. For example, if the price is $Y and the cost is $Z, the margin should be calculated as follows: 'Margin: X% (calculated as: (($Y - $Z) / $Y) × 100 = X%)'." if is_margin_request else ""}

RESPONSE FORMAT REQUIREMENTS:
1. For numerical values: Provide exact figures with relevant units:
   - Price/Cost: Include currency symbol (e.g., $25.99)
   - Dimensions: Include units (e.g., 750ml, 12.5cm)
   - Weight: Include units (e.g., 5.2 kg, 11.5 lbs)
   - Percentages: Include % symbol (e.g., 15.5%)
   - Inventory: Include "units" (e.g., 50 units)

2. For categorical data: Reference exact terms or values from the dataset:
   - Product status: Use exact status (e.g., ACTIVE, DRAFT, ARCHIVED)
   - Categories: Use exact category names from productType or tags
   - Wheels: Yes/No/No clear indication
   - Part Number: Exact SKU value

3. Missing Data: If a value is absent in the dataset, clearly state "information unavailable" (not "N/A")

4. Error Handling: If data is missing or unavailable for a requested field, indicate this clearly without making assumptions

5. Stick to what is explicitly provided - avoid assumptions where data is incomplete

6. MARGIN FORMULA: If user asks about margin calculation or formula, provide:
   "Profit margin is calculated using: Margin % = ((Selling Price - Cost) / Selling Price) × 100"

Field definitions:
- 'price' = customer-facing selling price from variant
- 'cost' = internal cost from inventory item  
- 'profit' = calculated profit (price - cost)
- 'margin' = calculated margin percentage ((profit/price) * 100)
- 'markup' = calculated markup (price / cost)
- 'inventory' = stock quantity
- 'dimensions' = product dimensions in order: length, width, height
- 'weight' = product weight with appropriate units
- 'wheels' = whether the product has wheels for mobility
- 'part_number' = SKU/part number/model number
- 'image_url' = main product image URL

Respond using only: {info_str}. 

For missing fields, state "information unavailable" clearly.
If 'image_url' is requested, return the direct image URL only once without markdown or formatting.
If margin formula is requested, include the calculation formula.
Use factual, precise language with exact values and appropriate units.
"""
    
    response = openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,  
        max_tokens=600  
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
        'markup': ['markup', 'mark up', 'mark-up', 'markups'],
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
            elif field == 'markup':
                return product_data.get('markup', 'N/A')
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
        model="gpt-3.5-turbo",
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


# UPDATED: Process single product with memory storage
def process_single_product(product_name_or_sku, requested_info, user_input):
    results = search_products(product_name_or_sku)
    products = results.get("data", {}).get("products", {}).get("edges", [])

    if not products:
        return "No product matched your query."
    elif len(products) > 1:
        # Multiple products found - ask for color/interior clarification
        st.session_state.awaiting_clarification = True
        st.session_state.clarification_type = "color_interior_specs"
        st.session_state.clarification_data = products
        st.session_state.original_query = user_input
        st.session_state.original_requested_info = requested_info
        return "I found multiple products matching your search. Could you please specify the color and interior option you're looking for?"
    else:
        # Single product found - check variants
        product = products[0]["node"]
        gid = product["id"]
        details = fetch_product_details_by_gid(gid)
        product_info = details["data"]["product"]

        variants = product_info.get("variants", {}).get("edges", [])
        if len(variants) > 1:
            # Multiple variants - ask for color/interior clarification at variant level
            st.session_state.awaiting_clarification = True
            st.session_state.clarification_type = "variant_color_interior"
            st.session_state.clarification_data = variants
            st.session_state.original_product = product_info
            st.session_state.original_query = user_input
            st.session_state.original_requested_info = requested_info
            return "This product has multiple variants. Could you please specify the color and interior option you're looking for?"
        else:
            # Single variant - process directly
            variant = variants[0]["node"] if variants else {}
            
            # Extract cost from inventory item
            cost = "N/A"
            if variant.get("inventoryItem") and variant["inventoryItem"].get("unitCost"):
                cost = variant["inventoryItem"]["unitCost"]["amount"]
            
            # Calculate profit and margin
            price = variant.get("price", "N/A")
            profit_margin_data = calculate_profit_and_margin(cost, price)
            markup_data = calculate_markup(cost, price)
            
            images = product_info.get("images", {}).get("edges", [])
            image_url = images[0]["node"]["url"] if images else "N/A"

            # Prepare enhanced product data
            enhanced_product_data = {
                "title": product_info.get("title"),
                "variant": variant,
                "cost": cost,
                "profit": profit_margin_data["profit"],
                "margin": profit_margin_data["margin"],
                "markup": markup_data["markup"],
                "image_url": image_url
            }

            # NEW: Store product in memory
            store_product_in_memory(product_info.get("title"), enhanced_product_data)

            answer = generate_ai_response(user_input, enhanced_product_data, requested_info)
            return answer


def handle_color_interior_clarification(user_input, products):
    """Handle clarification for any products based on color and interior specifications"""
    
    product_titles = [p["node"]["title"] for p in products]
    product_list_str = "\n".join(f"- {title}" for title in product_titles)
    
    prompt = f"""
The user is looking for a product and specified: "{user_input}"

Available products:
{product_list_str}

Find the product that best matches the user's specification. Look for the color or other specifications mentioned by the user in the product titles.

Be flexible with matching:
- Match colors regardless of case (Red = red = RED)
- Look for common abbreviations (Red = R, Blue = BLU, etc.)
- If user only mentions a color, match any product with that color
- If user mentions color + other specs, try to match both

Return JSON:
{{"matched_product_title": "exact title from the list", "confidence": "high"}}

If no clear match, return:
{{"matched_product_title": null, "confidence": "low"}}
"""
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo", 
            messages=[{"role": "user", "content": prompt}], 
            temperature=0, 
            max_tokens=300
        )
        result = eval(response.choices[0].message.content.strip())
        return result
    except:
        return {"matched_product_title": None, "confidence": "low"}



def handle_pelican_clarification(user_input, products):
    """Handle clarification for Pelican products based on color and interior specifications"""
    
    # Use GPT to match user's color/interior specification to available products
    product_titles = [p["node"]["title"] for p in products]
    product_list_str = "\n".join(f"- {title}" for title in product_titles)
    
    prompt = f"""
        The user is looking for a Pelican product and specified: "{user_input}"

        Available Pelican products:
        {product_list_str}

        Your task is to find the best matching product **ONLY if** the user's specified color and interior **both exist in the product title or SKU**.

        DO NOT try to guess or offer a similar product. If no product contains the actual color or interior mentioned by the user (e.g., "purple" or "velvet"), respond with:
        {"matched_product_title": null, "confidence": "low"}

        Examples:
        - If user says "purple" and no product has "purple", return null.
        - If user says "yellow with foam" and no product has both "yellow" and "foam", return null.

        Return only:
        {"matched_product_title": "...", "confidence": "high"}  — if match is exact
        {"matched_product_title": null, "confidence": "low"}  — if no exact match


        Color mappings:
        - Yellow/Yellow color = YLW
        - Orange/Orange color = OD  
        - Black/Black color = BLK
        - Clear/Transparent = CLR
        - Red/Red color = RED

        Interior options:
        - No Foam/Empty/Without foam = NFc
        - Foam/With foam = F
        - Dividers/With dividers = DIV
        - Padded/Padded dividers = PD

        Look for these patterns in the product SKUs and titles.

        Examples:
        - "black empty" should match products with "BLK" and "NF" 
        - "yellow with foam" should match products with "YLW" and "F"
        - "orange dividers" should match products with "OD" and "DIV"

        Return JSON like:
        {{"matched_product_title": "exact title from the list", "confidence": "high/medium/low"}}

        IMPORTANT: If no product contains the actual color or interior option mentioned by the user, do not guess. Always return null with "low" confidence.

        """
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo", 
            messages=[{"role": "user", "content": prompt}], 
            temperature=0, 
            max_tokens=300
        )
        result = eval(response.choices[0].message.content.strip())
        return result
    except:
        return {"matched_product_title": None, "confidence": "low"}



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
        markup_data = calculate_markup(cost, price)
        
        return {
            "title": product_info.get("title"),
            "variant": variant,
            "cost": cost,
            "profit": profit_margin_data["profit"],
            "margin": profit_margin_data["margin"],
            "markup": markup_data["markup"]
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


def handle_user_input_with_pelican_support(user_input):
    """Enhanced input handler with product memory and generic color/interior clarification support"""

    user_input = user_input.rstrip('?').strip()
    user_lower = user_input.lower()
    
    count_patterns = [
        r'how many products',
        r'total products',
        r'count.*products',
        r'number.*products',
        r'products.*count',
        r'products.*total',
        r'product.*total',
        r'product.*count',
    ]
    
    if any(re.search(pattern, user_lower) for pattern in count_patterns):
        count_result = get_total_product_count()
        return f"We have {count_result} on the site."
    
    # Check for margin formula requests
    margin_formula_patterns = [
        r'margin.*formula',
        r'how.*calculate.*margin',
        r'margin.*calculation',
        r'formula.*margin',
        r'calculate.*margin'
    ]
    
    if any(re.search(pattern, user_lower) for pattern in margin_formula_patterns):
        return "Profit margin is calculated using the formula: **Margin % = ((Selling Price - Cost) / Selling Price) × 100**\n\nFor example, if a product sells for $100 and costs $60:\nMargin % = (($100 - $60) / $100) × 100 = 40%"
    
    if extract_cost_update_intent(user_input):
        # Extract product name from the query
        product_name = extract_cost_update_product_name(user_input)
        
        # If no specific product name found, check if we have current product in memory
        if not product_name and st.session_state.current_product_memory:
            # User is asking about current product's cost update
            answer = process_cost_update_query(user_input, None)
            return answer
        elif product_name:
            # User specified a product
            answer = process_cost_update_query(user_input, product_name)
            return answer
        else:
            # No product specified and no current product in memory
            return "Please specify which product you'd like to check the cost update information for, or ask about a specific product first."

    # NEW: Check if user is asking about the current product in memory
    if (st.session_state.current_product_memory and 
        st.session_state.current_product_data and
        not st.session_state.awaiting_clarification):
        
        # Check if this is a new product request
        if is_new_product_request(user_input):
            # Clear memory and proceed with new product
            clear_product_memory()
        elif is_asking_about_current_product(user_input):
            # User is asking for more details about the current product
            requested_info = extract_current_product_info_request(user_input)
            current_data = st.session_state.current_product_data
            
            answer = generate_ai_response(user_input, current_data, requested_info)
            return answer

    if extract_cost_update_intent(user_input):
        # Check if asking about current product or specific product
        product_name = extract_cost_update_product_name(user_input)
        answer = process_cost_update_query(user_input, product_name)
        return answer


    # If awaiting color/interior specification for any product
    if (st.session_state.awaiting_clarification and
        st.session_state.clarification_type == "color_interior_specs"):

        products = st.session_state.clarification_data
        clarification_result = handle_color_interior_clarification(user_input, products)

        matched_title = clarification_result.get("matched_product_title", "")
        confidence = clarification_result.get("confidence", "")

        if clarification_result["matched_product_title"] and clarification_result["confidence"] == 'high':
            matched_product = next(
                (p for p in products if p["node"]["title"] == clarification_result["matched_product_title"]),
                None
            )

            if not matched_product:
                st.session_state.awaiting_clarification = False
                st.session_state.clarification_type = ""
                st.session_state.clarification_data = []
                st.session_state.original_query = ""
                st.session_state.original_requested_info = []
                return "Product with the specified color and interior combination is unavailable."

            # Fetch product details
            gid = matched_product["node"]["id"]
            details = fetch_product_details_by_gid(gid)
            product_info = details["data"]["product"]

            variants = product_info.get("variants", {}).get("edges", [])
            
            if len(variants) > 1:
                # Check if the user's input can already specify a variant
                variant_products = [{"node": {"title": v["node"]["title"]}} for v in variants]
                variant_clarification = handle_color_interior_clarification(user_input, variant_products)
                
                if variant_clarification.get("matched_product_title") and variant_clarification.get("confidence") == "high":
                    # Found a specific variant match - process it directly
                    matched_variant = next(
                        (v for v in variants if v["node"]["title"] == variant_clarification["matched_product_title"]),
                        None
                    )
                    if matched_variant:
                        selected_variant = matched_variant["node"]
                        
                        # Extract cost from inventory item
                        cost = "N/A"
                        if selected_variant.get("inventoryItem") and selected_variant["inventoryItem"].get("unitCost"):
                            cost = selected_variant["inventoryItem"]["unitCost"]["amount"]

                        price = selected_variant.get("price", "N/A")
                        profit_margin_data = calculate_profit_and_margin(cost, price)
                        markup_data = calculate_markup(cost, price)

                        images = product_info.get("images", {}).get("edges", [])
                        image_url = images[0]["node"]["url"] if images else "N/A"

                        enhanced_product_data = {
                            "title": product_info.get("title"),
                            "variant": selected_variant,
                            "cost": cost,
                            "profit": profit_margin_data["profit"],
                            "margin": profit_margin_data["margin"],
                            "markup": markup_data["markup"],
                            "image_url": image_url
                        }

                        # NEW: Store product in memory
                        store_product_in_memory(product_info.get("title"), enhanced_product_data)

                        original_query = st.session_state.original_query
                        original_requested_info = st.session_state.original_requested_info

                        answer = generate_ai_response(original_query, enhanced_product_data, original_requested_info)

                        # Reset state
                        st.session_state.awaiting_clarification = False
                        st.session_state.clarification_type = ""
                        st.session_state.clarification_data = []
                        st.session_state.original_query = ""
                        st.session_state.original_requested_info = []

                        return answer
                
                # Couldn't match variant from user input - ask for clarification
                st.session_state.awaiting_clarification = True
                st.session_state.clarification_type = "variant_color_interior"
                st.session_state.clarification_data = variants
                st.session_state.original_product = product_info
                return "This product has multiple variants. Could you please specify the color and interior option you're looking for?"
            
            else:
                variant = variants[0]["node"] if variants else {}

                # Extract cost from inventory item
                cost = "N/A"
                if variant.get("inventoryItem") and variant["inventoryItem"].get("unitCost"):
                    cost = variant["inventoryItem"]["unitCost"]["amount"]

                price = variant.get("price", "N/A")
                profit_margin_data = calculate_profit_and_margin(cost, price)
                markup_data = calculate_markup(cost, price)

                images = product_info.get("images", {}).get("edges", [])
                image_url = images[0]["node"]["url"] if images else "N/A"

                enhanced_product_data = {
                    "title": product_info.get("title"),
                    "variant": variant,
                    "cost": cost,
                    "profit": profit_margin_data["profit"],
                    "margin": profit_margin_data["margin"],
                    "markup": markup_data["markup"],
                    "image_url": image_url
                }

                # NEW: Store product in memory
                store_product_in_memory(product_info.get("title"), enhanced_product_data)

                original_query = st.session_state.original_query
                original_requested_info = st.session_state.original_requested_info

                answer = generate_ai_response(original_query, enhanced_product_data, original_requested_info)

                # Reset state
                st.session_state.awaiting_clarification = False
                st.session_state.clarification_type = ""
                st.session_state.clarification_data = []
                st.session_state.original_query = ""
                st.session_state.original_requested_info = []

                return answer

        # No match or low confidence
        st.session_state.awaiting_clarification = False
        st.session_state.clarification_type = ""
        st.session_state.clarification_data = []
        st.session_state.original_query = ""
        st.session_state.original_requested_info = []
        return "Product with the specified color and interior combination is unavailable."
    
    # If awaiting variant clarification based on color/interior
    if (st.session_state.awaiting_clarification and
        st.session_state.clarification_type == "variant_color_interior"):

        variants = st.session_state.clarification_data
        
        # Convert variants to the same format as products for the existing function
        variant_products = [{"node": {"title": v["node"]["title"]}} for v in variants]
        
        # Reuse the existing clarification function
        clarification_result = handle_color_interior_clarification(user_input, variant_products)

        matched_title = clarification_result.get("matched_product_title", "")
        confidence = clarification_result.get("confidence", "")

        if matched_title and confidence == 'high':
            matched_variant = next(
                (v for v in variants if v["node"]["title"] == matched_title),
                None
            )

            if not matched_variant:
                st.session_state.awaiting_clarification = False
                st.session_state.clarification_type = ""
                st.session_state.clarification_data = []
                st.session_state.original_query = ""
                st.session_state.original_requested_info = []
                st.session_state.original_product = None
                return "Variant with the specified color and interior combination is unavailable."

            # Process the matched variant
            selected_variant = matched_variant["node"]
            product = st.session_state.original_product

            # Extract cost from inventory item
            cost = "N/A"
            if selected_variant.get("inventoryItem") and selected_variant["inventoryItem"].get("unitCost"):
                cost = selected_variant["inventoryItem"]["unitCost"]["amount"]

            # Calculate profit and margin
            price = selected_variant.get("price", "N/A")
            profit_margin_data = calculate_profit_and_margin(cost, price)
            markup_data = calculate_markup(cost, price)

            images = product.get("images", {}).get("edges", [])
            image_url = images[0]["node"]["url"] if images else "N/A"

            # Prepare enhanced product data
            enhanced_product_data = {
                "title": product.get("title"),
                "variant": selected_variant,
                "cost": cost,
                "profit": profit_margin_data["profit"],
                "margin": profit_margin_data["margin"],
                "markup": markup_data["markup"],
                "image_url": image_url
            }

            # NEW: Store product in memory
            store_product_in_memory(product.get("title"), enhanced_product_data)

            original_query = st.session_state.original_query
            original_requested_info = st.session_state.original_requested_info

            answer = generate_ai_response(original_query, enhanced_product_data, original_requested_info)

            # Reset state
            st.session_state.awaiting_clarification = False
            st.session_state.clarification_type = ""
            st.session_state.clarification_data = []
            st.session_state.original_query = ""
            st.session_state.original_requested_info = []
            st.session_state.original_product = None

            return answer

        # No match or low confidence
        st.session_state.awaiting_clarification = False
        st.session_state.clarification_type = ""
        st.session_state.clarification_data = []
        st.session_state.original_query = ""
        st.session_state.original_requested_info = []
        st.session_state.original_product = None
        return "Variant with the specified color and interior combination is unavailable."
    
    # If awaiting product selection for cost update query
    if (st.session_state.awaiting_clarification and
        st.session_state.clarification_type == "cost_update_product_selection"):
        
        products = st.session_state.clarification_data
        clarification_result = handle_color_interior_clarification(user_input, products)
        
        if clarification_result.get("matched_product_title") and clarification_result.get("confidence") == 'high':
            matched_product = next(
                (p for p in products if p["node"]["title"] == clarification_result["matched_product_title"]),
                None
            )
            
            if matched_product:
                gid = matched_product["node"]["id"]
                details = fetch_product_details_by_gid(gid)
                product_info = details["data"]["product"]
                
                updated_at = product_info.get("updatedAt", "N/A")
                product_title = product_info.get("title", "Unknown Product")
                
                if updated_at != "N/A":
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                        formatted_date = dt.strftime("%B %d, %Y at %I:%M %p UTC")
                        answer = f"The product '{product_title}' was last updated on {formatted_date}. Note: Shopify tracks product updates, not specifically cost updates."
                    except:
                        answer = f"The product '{product_title}' was last updated at {updated_at}. Note: Shopify tracks product updates, not specifically cost updates."
                else:
                    answer = f"Update information is not available for '{product_title}'."
                
                # Reset clarification state
                st.session_state.awaiting_clarification = False
                st.session_state.clarification_type = ""
                st.session_state.clarification_data = []
                st.session_state.original_query = ""
                
                return answer
        
        # No match found
        st.session_state.awaiting_clarification = False
        st.session_state.clarification_type = ""
        st.session_state.clarification_data = []
        st.session_state.original_query = ""
        return "Could not find the specified product to check cost update information."

    if not is_product_related_query(user_input):
        return generate_general_response(user_input)

    # If not awaiting clarification, proceed with normal flow
    return handle_user_input(user_input)


# Streamlit UI
st.title("🛍️ Conversational Shopify Chatbot")
user_input = st.chat_input("Ask about a product...")

if user_input:
    try:
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
            answer = handle_user_input_with_pelican_support(user_input)
            st.session_state.conversation.append(("bot", answer))

    except Exception as e:
        # Log the error for debugging (optional - remove in production)
        print(f"Error occurred: {str(e)}")
        
        # Display user-friendly error message
        error_message = "An error occurred. Please refresh the page and try again."
        st.session_state.conversation.append(("bot", error_message))
        
        # Reset session state to prevent cascading errors
        st.session_state.awaiting_clarification = False
        st.session_state.clarification_type = ""
        st.session_state.clarification_data = []
        st.session_state.original_query = ""
        st.session_state.original_requested_info = []
        st.session_state.original_product = None

    
# Display chat
for role, message in st.session_state.conversation:
    if role == "bot":
        st.chat_message(role).text(message)  # Use .text() instead of .write()
    else:
        st.chat_message(role).write(message)
