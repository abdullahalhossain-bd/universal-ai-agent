<?php
$autoload = __DIR__ . '/stripe/stripe/init.php';
if (!is_file($autoload)) {
    throw new RuntimeException('Stripe SDK is missing. Install the Stripe dependency before enabling payments.');
}
require_once $autoload;

$publishableKey = getenv('STRIPE_PUBLISHABLE_KEY') ?: '';
$secretKey = getenv('STRIPE_SECRET_KEY') ?: '';

if ($publishableKey === '' || $secretKey === '') {
    throw new RuntimeException('Stripe credentials are not configured. Set STRIPE_PUBLISHABLE_KEY and STRIPE_SECRET_KEY.');
}

\Stripe\Stripe::setApiKey($secretKey);
