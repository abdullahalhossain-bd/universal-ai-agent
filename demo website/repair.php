<?php
if (session_status() !== PHP_SESSION_ACTIVE) session_start();
include_once('./includes/restriction.php');
include_once('./includes/headerNav.php');

if (!isset($_SESSION['id']) || !ctype_digit((string)$_SESSION['id'])) {
    header('Location: login.php?unauthorizedAccess');
    exit;
}

include './includes/config.php';

function repairEsc($value): string {
    return htmlspecialchars((string)$value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

$uid = (int)$_SESSION['id'];
$limit = 4;
$page = isset($_GET['page']) && ctype_digit((string)$_GET['page']) ? max(1, (int)$_GET['page']) : 1;

$countStmt = $conn->prepare('SELECT COUNT(*) AS total FROM repair WHERE user_id = ?');
$countStmt->bind_param('i', $uid);
$countStmt->execute();
$total = (int)($countStmt->get_result()->fetch_assoc()['total'] ?? 0);
$countStmt->close();

$totalPages = max(1, (int)ceil($total / $limit));
if ($page > $totalPages) $page = $totalPages;
$offset = ($page - 1) * $limit;

$stmt = $conn->prepare('SELECT p_name, category, damage_type, uuid, advance_amt, booked_date, return_date, due, status FROM repair WHERE user_id = ? ORDER BY booked_date DESC LIMIT ?, ?');
$stmt->bind_param('iii', $uid, $offset, $limit);
$stmt->execute();
$result = $stmt->get_result();
?>
<h4>My Repair Requests</h4><br>
<?php if ($result->num_rows > 0): ?>
<div class="table-cont"><table><tr><th class="short">S.N</th><th class="medium">Product</th><th class="medium">Category</th><th class="medium">Damage Type</th><th class="medium">UUID</th><th class="short">Advance</th><th class="short">Booked</th><th class="short">Return</th><th class="short">Due</th><th class="short">Status</th></tr>
<?php $sn=$offset; while($row=$result->fetch_assoc()): $sn++; ?><tr><td><?php echo $sn; ?></td><td><?php echo repairEsc($row['p_name']); ?></td><td><?php echo repairEsc($row['category']); ?></td><td><?php echo repairEsc($row['damage_type']); ?></td><td><?php echo repairEsc($row['uuid']); ?></td><td><?php echo repairEsc($row['advance_amt']); ?></td><td><?php echo repairEsc($row['booked_date']); ?></td><td><?php echo repairEsc($row['return_date']); ?></td><td><?php echo repairEsc($row['due']); ?></td><td><?php echo repairEsc($row['status']); ?></td></tr><?php endwhile; ?></table></div>
<?php else: ?><p>No repair requests found.</p><?php endif; ?>

<?php if ($total > 0): ?><div class="pagination"><?php for($i=1;$i<=$totalPages;$i++): ?><a href="repair.php?page=<?php echo $i; ?>" class="<?php echo $page===$i?'active':''; ?>"><?php echo $i; ?></a><?php endfor; ?></div><?php endif; ?>
<?php $stmt->close(); $conn->close(); ?>