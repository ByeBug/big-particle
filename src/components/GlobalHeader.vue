<template>
  <el-row class="header-container">
    <el-col class="logo-div" :span="8">
      <img src="@/assets/矿业公司logo.jpg" alt="logo" />
    </el-col>
    <el-col class="header-middle" :span="8">
      <div class="title">大颗粒检测系统</div>
    </el-col>
    <el-col class="header-right" :span="8"></el-col>
  </el-row>
</template>

<style scoped>
.header-container {
  height: 100%;
}
.logo-div {
  height: 100%;

  img {
    height: 100%;
  }
}
.header-middle {
  display: flex;
  align-items: center;
  justify-content: center;
}
.title {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: 4px;
  user-select: none;
}
.title::before,
.title::after {
  content: '';
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 1px;
  background: var(--el-color-primary);
  margin: 0 8px;
  transform: rotate(45deg);
}
.header-right {
  text-align: right;
}
</style>
