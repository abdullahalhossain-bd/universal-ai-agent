<?php
if (session_status() !== PHP_SESSION_ACTIVE) session_start();
if (!isset($_SESSION['id']) || !ctype_digit((string)$_SESSION['id'])) {
    header('Location: index.php?UnauthorizedUser');
    exit;
}
include_once('./includes/config.php');
include_once('./includes/headerNav.php');

function profileEsc($value): string {
    return htmlspecialchars((string)$value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

$uid = (int)$_SESSION['id'];

if (isset($_POST['delete'])) {
    $stmt = $conn->prepare("DELETE FROM soldproducts WHERE uid = ? AND status = 'delivered'");
    if ($stmt) {
        $stmt->bind_param('i', $uid);
        $stmt->execute();
        $stmt->close();
    }
    header('Location: profile.php?deliveredHistoryDeleted=1');
    exit;
}

if (isset($_POST['save'])) {
    if (isset($_POST['name'], $_POST['email']) && trim((string)$_POST['name']) !== '' && trim((string)$_POST['email']) !== '') {
        $name = trim((string)$_POST['name']);
        $email = trim((string)$_POST['email']);
        if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
            header('Location: profile.php?error=invalidemail');
            exit;
        }
        $stmt = $conn->prepare('UPDATE customer SET customer_fname = ?, customer_email = ? WHERE customer_id = ?');
        $stmt->bind_param('ssi', $name, $email, $uid);
        $stmt->execute();
        $stmt->close();
        header('Location: profile.php?profileUpdatedSuccessfully=1');
        exit;
    }
    if (isset($_POST['address']) && trim((string)$_POST['address']) !== '') {
        $address = trim((string)$_POST['address']);
        $stmt = $conn->prepare('UPDATE customer SET customer_address = ? WHERE customer_id = ?');
        $stmt->bind_param('si', $address, $uid);
        $stmt->execute();
        $stmt->close();
        header('Location: profile.php?profileUpdatedSuccessfully=1');
        exit;
    }
    if (isset($_POST['number']) && trim((string)$_POST['number']) !== '') {
        $number = trim((string)$_POST['number']);
        if (!preg_match('/^[0-9+()\-\s]{7,20}$/', $number)) {
            header('Location: profile.php?error=enterValidNumber');
            exit;
        }
        $stmt = $conn->prepare('UPDATE customer SET customer_phone = ? WHERE customer_id = ?');
        $stmt->bind_param('si', $number, $uid);
        $stmt->execute();
        $stmt->close();
        header('Location: profile.php?profileUpdatedSuccessfully=1');
        exit;
    }
}

$stmt = $conn->prepare('SELECT customer_fname, customer_email, customer_phone, customer_address, customer_role FROM customer WHERE customer_id = ? LIMIT 1');
$stmt->bind_param('i', $uid);
$stmt->execute();
$user = $stmt->get_result()->fetch_assoc();
$stmt->close();
if (!$user) {
    session_destroy();
    header('Location: index.php?UnauthorizedUser');
    exit;
}

$_SESSION['customer_name'] = $user['customer_fname'];
$_SESSION['customer_email'] = $user['customer_email'];
$_SESSION['customer_phone'] = $user['customer_phone'];
$_SESSION['customer_address'] = $user['customer_address'];
$_SESSION['customer_role'] = $user['customer_role'];

$stmt = $conn->prepare("SELECT * FROM soldproducts WHERE uid = ? ORDER BY date DESC");
$stmt->bind_param('i', $uid);
$stmt->execute();
$orders = $stmt->get_result();
$stmt->close();

$stmt = $conn->prepare("SELECT COUNT(*) AS total FROM soldproducts WHERE uid = ? AND status = 'delivered'");
$stmt->bind_param('i', $uid);
$stmt->execute();
$deliveredCount = (int)($stmt->get_result()->fetch_assoc()['total'] ?? 0);
$stmt->close();

$stmt = $conn->prepare('SELECT * FROM repair WHERE user_id = ? ORDER BY booked_date DESC');
$stmt->bind_param('i', $uid);
$stmt->execute();
$repairs = $stmt->get_result();
?>
<head><style>
.edit-container{display:flex;justify-content:center;gap:2%;flex-wrap:wrap}.edit-card{border:none;color:rgb(32,69,32);background:aliceblue;width:25%;padding:1rem;overflow:hidden}.profile_edit,.address_edit,.contact_edit{display:none}.show{display:inline}@media(max-width:700px){.edit-card{width:85%;margin-bottom:5%}}
table{border-collapse:collapse}th,td{padding:6px}th{background:grey}
</style></head>
<h4 style="text-align:center">Manage My Account</h4>
<div class="edit-container">
<div class="edit-card"><h4>Personal Profile <a href="#/profile/edit" id="edit_link1">Edit</a></h4><div class="profile_edit"><form action="profile.php" method="post"><label>New name</label><input type="text" name="name" maxlength="100"><label>New email</label><input type="email" name="email" maxlength="254"><button type="submit" name="save" class="btn-info">Save</button></form></div><h5><?php echo profileEsc($user['customer_fname']) . ' (' . profileEsc($user['customer_role']) . ')'; ?></h5><h5><?php echo profileEsc($user['customer_email']); ?></h5><?php if($user['customer_role']==='admin'): ?><h4>Go to Admin Panel</h4><a id="admin" href="admin/login.php">Admin</a><?php endif; ?></div>
<div class="edit-card"><h4>Address Book <a href="#/address/edit" id="edit_link2">Edit</a></h4><div class="address_edit"><form action="profile.php" method="post"><label>New address</label><input type="text" name="address" maxlength="500"><button type="submit" name="save" class="btn-info">Save</button></form></div><h5><?php echo profileEsc($user['customer_address']); ?></h5></div>
<div class="edit-card"><h4>Contact Book <a href="#/contact/edit" id="edit_link3">Edit</a></h4><div class="contact_edit"><form action="profile.php" method="post"><label>New number</label><input type="text" name="number" maxlength="20"><button type="submit" name="save" class="btn-info">Save</button></form></div><h5><?php echo profileEsc($user['customer_phone']); ?></h5></div>
</div>
<hr class="soften">
<div style="text-align:center"><h4>Order History</h4>
<?php if($deliveredCount > 0): ?><form action="profile.php" method="post"><button name="delete" type="submit" class="btn btn-danger" onclick="return confirm('Delete delivered order history?')">Delete Delivered History</button></form><?php endif; ?>
<table style="width:90%;margin:auto"><tr><th>S.N</th><th>Image</th><th>Product</th><th>Price</th><th>Quantity</th><th>UUID</th><th>Date</th><th>Status</th></tr>
<?php $sn=0; while($order=$orders->fetch_assoc()): $sn++; ?>
<tr>
<td><?php echo $sn; ?></td>
<td><?php $pid=(int)$order['pid']; $p=$conn->query("SELECT product_img, product_title FROM products WHERE product_id=".$pid." LIMIT 1)->fetch_assoc(); ?><img class="image" style="height:50px;width:50px" src="admin/upload/<?php echo profileEsc($p['product_img'] ?? ''); ?>" alt="<?php echo profileEsc($p['product_title'] ?? 'Product'); ?>"></td>
<td><?php echo profileEsc($p['product_title'] ?? 'Product unavailable'); ?></td><td><?php echo profileEsc($order['price']); ?></td><td><?php echo profileEsc($order['quantity']); ?></td><td><?php echo profileEsc($order['uuid'] ?? ''); ?></td><td><?php echo profileEsc($order['date']); ?></td><td><?php echo profileEsc($order['status']); ?></td>
</tr>
<?php endwhile; ?></table>

<h4>Repair History</h4>
<table style="width:90%;margin:auto"><tr><th>S.N</th><th>Product</th><th>Category</th><th>Issue</th><th>Advance</th><th>UUID</th><th>Due</th><th>Booked</th><th>Status</th><th>Return Date</th></tr>
<?php $sn=0; while($repair=$repairs->fetch_assoc()): $sn++; ?><tr><td><?php echo $sn; ?></td><td><?php echo profileEsc($repair['p_name']); ?></td><td><?php echo profileEsc($repair['category']); ?></td><td><?php echo profileEsc($repair['damage_type']); ?></td><td><?php echo profileEsc($repair['advance_amt']); ?></td><td><?php echo profileEsc($repair['uuid']); ?></td><td><?php echo profileEsc($repair['due']); ?></td><td><?php echo profileEsc($repair['booked_date']); ?></td><td><?php echo profileEsc($repair['status']); ?></td><td><?php echo profileEsc($repair['return_date']); ?></td></tr><?php endwhile; ?></table>
</div>
<?php $conn->close(); include_once('./includes/footer.php'); ?>
<script src="./js/jquery.js"></script><script src="./js/bootstrap.min.js"></script><script src="./js/edit.js"></script>