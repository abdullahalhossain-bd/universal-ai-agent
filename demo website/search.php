<?php
include_once('./includes/headerNav.php');
include_once('./includes/config.php');

$search_term = '';
if (isset($_POST['search'])) {
    $search_term = trim((string)$_POST['search']);
} elseif (isset($_GET['search'])) {
    $search_term = trim((string)$_GET['search']);
}

$category = isset($_GET['catag']) ? trim((string)$_GET['catag']) : '';
$page = isset($_GET['page']) && ctype_digit((string)$_GET['page']) ? max(1, (int)$_GET['page']) : 1;
$limit = 8;

if ($search_term === '' && $category === '') {
    echo "<h4 style='color:red; margin-left:8%;border:1px solid aliceblue'>Please enter a search term.</h4>";
    $conn->close();
    exit;
}

$conditions = [];
$params = [];
types = '';

if ($search_term !== '') {
    $tokens = preg_split('/\s+/u', $search_term, -1, PREG_SPLIT_NO_EMPTY);
    foreach ($tokens as $token) {
        $conditions[] = '(product_title LIKE ? OR product_catag LIKE ? OR product_desc LIKE ?)';
        $like = '%' . $token . '%';
        $params[] = $like;
        $params[] = $like;
        $params[] = $like;
        $types .= 'sss';
    }
}

if ($category !== '') {
    $conditions[] = 'product_catag LIKE ?';
    $params[] = '%' . $category . '%';
    $types .= 's';
}

$where = implode(' AND ', $conditions);

$countSql = "SELECT COUNT(*) AS total FROM products WHERE {$where}";
$countStmt = $conn->prepare($countSql);
if (!$countStmt) {
    http_response_code(500);
    exit('Search temporarily unavailable.');
}
if ($types !== '') {
    $countStmt->bind_param($types, ...$params);
}
$countStmt->execute();
$countResult = $countStmt->get_result()->fetch_assoc();
$totalProducts = (int)($countResult['total'] ?? 0);
$countStmt->close();

$totalPages = max(1, (int)ceil($totalProducts / $limit));
if ($page > $totalPages) {
    $page = $totalPages;
}
$offset = ($page - 1) * $limit;

$sql = "SELECT product_id, product_title, product_catag, product_desc, product_price, product_img, product_date
        FROM products WHERE {$where} ORDER BY product_id DESC LIMIT ?, ?";
$stmt = $conn->prepare($sql);
if (!$stmt) {
    http_response_code(500);
    exit('Search temporarily unavailable.');
}

$queryTypes = $types . 'ii';
$queryParams = $params;
$queryParams[] = $offset;
$queryParams[] = $limit;
$stmt->bind_param($queryTypes, ...$queryParams);
$stmt->execute();
$result = $stmt->get_result();

function searchEsc($value): string {
    return htmlspecialchars((string)$value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

$displaySearch = searchEsc($search_term !== '' ? $search_term : $category);
?>

<div class="dynamic-data-container-search">
    <span><h3 style="color:grey;margin-left:2.4%">Search: <?php echo $displaySearch; ?></h3></span>

<?php
if ($result->num_rows > 0) {
    while ($row = $result->fetch_assoc()) {
        $id = (int)$row['product_id'];
        $title = searchEsc($row['product_title']);
        $date = searchEsc($row['product_date']);
        $desc = searchEsc($row['product_desc']);
        $img = searchEsc($row['product_img']);
        $price = searchEsc($row['product_price']);
?>
<a href="product.php?id=<?php echo $id; ?>">
    <div class="product">
        <img class="image" src="admin/upload/<?php echo $img; ?>" alt="<?php echo $title; ?>" loading="lazy">
        <div class="detail-cont">
            <h5 class="title"><?php echo $title; ?> <p class="date"><?php echo $date; ?></p></h5>
            <p class="description"><?php echo $desc; ?></p>
            <p class="price"><b>Rs.<?php echo $price; ?></b></p>
        </div>
    </div>
</a>
<?php
    }
} else {
    echo "<h4 style='color:red; margin-left:8%;border:1px solid aliceblue'>No products found.</h4>";
}
$stmt->close();
$conn->close();
?>
</div>

<?php if ($totalProducts > 0): ?>
<div class="pag-cont-search">
    <div class="pagination">
        <?php for ($i = 1; $i <= $totalPages; $i++): ?>
            <?php
            $query = ['page' => $i];
            if ($search_term !== '') $query['search'] = $search_term;
            if ($category !== '') $query['catag'] = $category;
            $url = 'search.php?' . http_build_query($query);
            ?>
            <a href="<?php echo searchEsc($url); ?>" class="<?php echo $page === $i ? 'active' : ''; ?>"><?php echo $i; ?></a>
        <?php endfor; ?>
    </div>
</div>
<?php endif; ?>