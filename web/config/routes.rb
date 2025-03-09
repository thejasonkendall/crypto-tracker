Rails.application.routes.draw do
  root 'wallet#index'
  get 'wallet', to: 'wallet#index'
  
  # Keep your existing routes
end