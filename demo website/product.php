<?php
include_once('./includes/config.php');
include_once('./stripeConfig.php');
if (session_status() !== PHP_SESSION_ACTIVE) {
    session_start();
}

function productEsc($value): string {
    return htmlspecialchars((string)$value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

if (!isset($_GET['id']) || !ctype_digit((string)$_GET['id']) || (int)$_GET['id'] < 1) {
    http_response_code(404);
    exit('Product not found.');
}

$productId = (int)$_GET['id'];
$stmt = $conn->prepare('SELECT * FROM products WHERE product_id = ? LIMIT 1');
if (!$stmt) {
    http_response_code(500);
    exit('Product temporarily unavailable.');
}
$stmt->bind_param('i', $productId);
$stmt->execute();
$result = $stmt->get_result();
$product = $result->fetch_assoc();
$stmt->close();

if (!$product) {
    http_response_code(404);
    exit('Product not found.');
}

if (isset($_POST['addToCart'])) {
    if (!isset($_SESSION['id'])) {
        header('Location: login.php?LoginFirst');
        exit;
    }

    $quantity = filter_var($_POST['quantity'] ?? 1, FILTER_VALIDATE_INT, [
        'options' => ['min_range' => 1, 'max_range' => 5]
    ]);
    if ($quantity === false) {
        $quantity = 1;
    }

    // Never trust price/title values from the browser/session; use the database row fetched above.
    $cartStmt = $conn->prepare('INSERT INTO carts (pid, uid, product, price, quantity) VALUES (?, ?, ?, ?, ?)');
    if (!$cartStmt) {
        http_response_code(500);
        exit('Cart is temporarily unavailable.');
    }
    $uid = (int)$_SESSION['id'];
    $title = (string)$product['product_title'];
    $price = (float)$product['product_price'];
    $cartStmt->bind_param('iisdi', $productId, $uid, $title, $price, $quantity);
    $cartStmt->execute();
    $cartStmt->close();
    header('Location: product.php?id=' . $productId . '&added=1');
    exit;
}

include_once('./includes/headerNav.php');

$img = productEsc($product['product_img']);
$title = productEsc($product['product_title']);
$date = productEsc($product['product_date']);
$description = productEsc($product['product_desc']);
$price = productEsc($product['product_price']);
?>
<head>
<style>
.selected_product{margin-top:5%;display:flex;justify-content:center}.prod-in{position:relative;width:60%}#image-pr{height:80%;width:50%}.img-magnifier-container{position:absolute;top:8%;left:2%;width:90%;height:100%}.detail-cont-pr{position:relative;left:49%;top:15%;width:50%;display:flex;flex-direction:column;align-items:center;justify-content:center}.img-magnifier-glass{position:absolute;left:25%;opacity:.1;border-radius:5%;cursor:none;width:20px;height:20px}.img-magnifier-glass:hover{opacity:1;border-radius:10%;width:100px;height:100px}.price,.discount{text-align:center}.description-pr{width:100%;overflow-y:hidden;text-align:center;color:grey;font-size:medium;font-family:cursive}.btn-pr{display:flex;gap:4px}.button{border:none;color:white;padding:16px;text-align:center;text-decoration:none;font-size:16px;margin:1px;transition-duration:.4s;cursor:pointer;box-shadow:0 8px 16px 0 rgba(0,0,0,.2),0 6px 20px 0 rgba(0,0,0,.19)}.button:hover{transform:scale(1.05)}.btn2{background-color:#E74C3C}.btn1{background-color:#40E0D0}.quantityDiv{display:flex;align-items:center;justify-content:center;gap:6px;margin-bottom:20px}.section-title{margin:0;padding:0;font-size:14px}.addSub{height:30px;width:30px;background:#C0C0C0;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:24px}@media(max-width:700px){.prod-in{width:100%}.detail-cont-pr{position:relative;left:0;width:100%;top:0}.img-magnifier-container{position:relative;left:0;top:0;width:100%;height:auto}#image-pr{width:100%;height:auto}}
</style>
<script>
function magnify(imgID, zoom){var img=document.getElementById(imgID);if(!img)return;var glass=document.createElement('DIV');glass.className='img-magnifier-glass';img.parentElement.insertBefore(glass,img);glass.style.backgroundImage="url('"+img.src.replace(/'/g,"%27")+"')";glass.style.backgroundRepeat='no-repeat';glass.style.backgroundSize=(img.width*zoom)+'px '+(img.height*zoom)+'px';var bw=3,w=glass.offsetWidth/2,h=glass.offsetHeight/2;function move(e){e.preventDefault();var a=img.getBoundingClientRect(),x=(e.clientX-a.left),y=(e.clientY-a.top);x=Math.max(w/zoom,Math.min(x,img.width-w/zoom));y=Math.max(h/zoom,Math.min(y,img.height-h/zoom));glass.style.left=(x-w)+'px';glass.style.top=(y-h)+'px';glass.style.backgroundPosition='-'+((x*zoom)-w+bw)+'px -'+((y*zoom)-h+bw)+'px'}glass.addEventListener('mousemove',move);img.addEventListener('mousemove',move)}
</script>
</head>
<body>
<?php if (isset($_GET['added'])): ?><h4 style="text-align:center;color:green">Product added to your cart.</h4><?php endif; ?>
<div class="selected_product"><div class="prod-in">
<div class="img-magnifier-container"><img id="image-pr" src="admin/upload/<?php echo $img; ?>" alt="<?php echo $title; ?>" loading="lazy"></div>
<div class="detail-cont-pr">
<h5 class="title"><?php echo $title; ?> <p class="date"><?php echo $date; ?></p></h5>
<p class="description-pr"><?php echo $description; ?></p>
<p class="price"><b>Rs.<?php echo $price; ?></b></p>
<form action="product.php?id=<?php echo $productId; ?>" method="post">
<div class="quantityDiv"><h6 class="section-title">Quantity</h6><button type="button" class="addSub" onclick="decQuantity()" aria-label="Decrease quantity">-</button><input id="quantity" name="quantity" style="margin:0;padding:0;width:50px;border:none;height:30px;text-align:center" type="number" min="1" max="5" value="1" autocomplete="off"><button type="button" class="addSub" onclick="incQuantity()" aria-label="Increase quantity">+</button></div>
<div class="btn-pr"><a href="payment.php?id=<?php echo $productId; ?>" class="button btn1">Purchase</a><?php if(isset($_SESSION['id'])): ?><button type="submit" name="addToCart" class="button btn2">Add To Cart</button><?php else: ?><a href="login.php?LoginFirst" class="button btn2">Add To Cart</a><?php endif; ?></div>
</form>
</div></div></div>
<script>
function incQuantity(){var q=document.getElementById('quantity');q.value=Math.min(5,parseInt(q.value||1,10)+1)}
function decQuantity(){var q=document.getElementById('quantity');q.value=Math.max(1,parseInt(q.value||1,10)-1)}
magnify('image-pr',3);
</script>
</body>