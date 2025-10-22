#!/bin/bash

# --- Configuration ---
TORSITE_DIR="/home/z3r0/projects/Ghost_Comm/NODES/torsite"
NGINX_BASE_PORT=8080  # Starting local port for nginx
NUM_SERVICES=6
TORRC_PATH="/etc/tor/torrc"
NGINX_SITES_AVAILABLE="/etc/nginx/sites-available"
NGINX_SITES_ENABLED="/etc/nginx/sites-enabled"

declare -A ONION_ADDRESSES

echo "--- Setting up $NUM_SERVICES Tor Hidden Services ---"

# Create main directory
mkdir -p "$TORSITE_DIR"

for i in $(seq 1 $NUM_SERVICES); do
    TOR_DATA_DIR="$TORSITE_DIR/tor_data_node$i"
    HTML_DIR="$TORSITE_DIR/html_node$i"
    NGINX_CONF_PATH="$TORSITE_DIR/nginx_node$i.conf"
    NGINX_SITE_NAME="torsite_node$i"

    # 1. Create directories
    echo "Creating directories for node $i: $TOR_DATA_DIR, $HTML_DIR"
    mkdir -p "$TOR_DATA_DIR" "$HTML_DIR"

    # 2. Permissions
    sudo chown debian-tor:debian-tor "$TOR_DATA_DIR"
    sudo chmod 700 "$TOR_DATA_DIR"

    # 3. Generate Nginx configuration
    PORT=$((NGINX_BASE_PORT + i - 1))
    echo "Generating Nginx config for node $i on port $PORT"
    cat <<EOF > "$NGINX_CONF_PATH"
server {
    listen 127.0.0.1:$PORT;
    server_name localhost;

    root $HTML_DIR;
    index index.html index.htm;

    location / {
        try_files \$uri \$uri/ =404;
    }

    add_header X-Frame-Options "DENY";
    add_header X-Content-Type-Options "nosniff";
    add_header X-XSS-Protection "1; mode=block";
    add_header Referrer-Policy "no-referrer";
}
EOF

    # 4. Symlink for Nginx
    sudo ln -sf "$NGINX_CONF_PATH" "$NGINX_SITES_AVAILABLE/$NGINX_SITE_NAME"
    sudo ln -sf "$NGINX_SITES_AVAILABLE/$NGINX_SITE_NAME" "$NGINX_SITES_ENABLED/$NGINX_SITE_NAME"

    # 5. Placeholder HTML
    cat <<EOF > "$HTML_DIR/index.html"
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Hidden Service Node $i</title>
</head>
<body>
<h1>Node $i Hidden Service</h1>
<p>This is node $i of $NUM_SERVICES.</p>
</body>
</html>
EOF

    # 6. Tor Hidden Service config
    if ! grep -q "HiddenServiceDir $TOR_DATA_DIR" "$TORRC_PATH"; then
        sudo bash -c "cat <<EOT >> $TORRC_PATH

# Hidden Service Node $i
HiddenServiceDir $TOR_DATA_DIR
HiddenServicePort 80 127.0.0.1:$PORT
EOT"
    fi
done

# 7. Restart services
echo "Restarting Tor and Nginx..."
sudo systemctl restart tor
sudo systemctl restart nginx

# 8. Wait and retrieve .onion addresses
echo "Waiting for Tor to generate hostname files..."
sleep 10

for i in $(seq 1 $NUM_SERVICES); do
    TOR_DATA_DIR="$TORSITE_DIR/tor_data_node$i"
    if [ -f "$TOR_DATA_DIR/hostname" ]; then
        ONION=$(cat "$TOR_DATA_DIR/hostname")
        ONION_ADDRESSES[$i]=$ONION
        echo "Node $i .onion address: http://$ONION"
    else
        echo "Error: hostname not found for node $i. Check Tor logs."
    fi
done

echo "All hidden services setup complete!"

