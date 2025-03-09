class WalletController < ApplicationController
    def index
      # You can either use your zpub or a standard BTC address
      # For zpub, the service will return demo values until properly implemented
      wallet_address = 'zpub6rweK1frBXkw4GdMHRBuU24zJ4tCaJowe28tFQaynarF9DcUv6nBsGNnMqSGbrFk3Fz6Tze4KjiaKgJ4nzTUY1dpp6476QvvxsmTHMgeKsK'
      
      # Alternative: Use a standard BTC address for testing
      # wallet_address = 'bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh' # Example address
      
      begin
        service = BitcoinWalletService.new(wallet_address)
        @btc_balance = service.get_balance
        @usd_value = service.get_usd_value(@btc_balance)
        @wallet_address = wallet_address
      rescue => e
        flash.now[:error] = "Could not retrieve wallet information: #{e.message}"
        @btc_balance = 0
        @usd_value = 0
        @wallet_address = wallet_address
      end
    end
  end