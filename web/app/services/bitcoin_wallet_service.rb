class BitcoinWalletService
    include HTTParty
    
    def initialize(wallet_address)
      @wallet_address = wallet_address
      @is_xpub = wallet_address.start_with?('xpub', 'ypub', 'zpub')
    end
  
    def get_balance
      if @is_xpub
        get_balance_for_xpub
      else
        get_balance_for_address
      end
    end
    
    def get_balance_for_xpub
      # Trezor's Blockbook API can work directly with xpub/ypub/zpub
      response = HTTParty.get("https://btc1.trezor.io/api/v2/xpub/#{@wallet_address}")
      
      if response.success?
        data = JSON.parse(response.body)
        # Balance comes in satoshis
        balance_btc = data['balance'].to_f / 100_000_000
        return balance_btc
      else
        # Try fallback server if the first one fails
        fallback_response = HTTParty.get("https://btc2.trezor.io/api/v2/xpub/#{@wallet_address}")
        
        if fallback_response.success?
          data = JSON.parse(fallback_response.body)
          balance_btc = data['balance'].to_f / 100_000_000
          return balance_btc
        else
          raise "Error fetching xpub balance from Trezor API: #{response.code} #{response.message}"
        end
      end
    end
    
    def get_balance_for_address
      # For regular Bitcoin addresses, use Blockstream API
      response = HTTParty.get("https://blockstream.info/api/address/#{@wallet_address}")
      
      if response.success?
        # Get transactions for the address
        tx_response = HTTParty.get("https://blockstream.info/api/address/#{@wallet_address}/txs")
        
        if tx_response.success?
          # Calculate balance from transactions
          balance_satoshis = 0
          
          JSON.parse(tx_response.body).each do |tx|
            tx["vout"].each do |output|
              if output["scriptpubkey_address"] == @wallet_address
                balance_satoshis += output["value"]
              end
            end
          end
          
          # Convert satoshis to BTC
          balance_btc = balance_satoshis.to_f / 100_000_000
          return balance_btc
        else
          raise "Error fetching transactions: #{tx_response.code} #{tx_response.message}"
        end
      else
        raise "Error fetching address: #{response.code} #{response.message}"
      end
    end
  
    def get_usd_value(btc_amount)
      # Using CoinGecko API for price data
      price_response = HTTParty.get('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd')
      
      if price_response.success?
        price_data = JSON.parse(price_response.body)
        usd_price = price_data['bitcoin']['usd']
        return btc_amount * usd_price
      else
        # Try fallback price source if CoinGecko fails
        begin
          # Blockstream doesn't provide price data, so try Binance API as fallback
          binance_response = HTTParty.get('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT')
          
          if binance_response.success?
            binance_data = JSON.parse(binance_response.body)
            usd_price = binance_data['price'].to_f
            return btc_amount * usd_price
          else
            raise "Error fetching BTC price from fallback: #{binance_response.code}"
          end
        rescue => e
          raise "Error fetching BTC price: #{e.message}"
        end
      end
    end
  end