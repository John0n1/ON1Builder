// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@aave/core-v3/contracts/flashloan/base/FlashLoanReceiverBase.sol";
import "@aave/core-v3/contracts/interfaces/IPoolAddressesProvider.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/**
 * @title SimpleFlashloan
 * @notice A basic flashloan receiver contract for Aave V3
 * @dev All complex logic is handled by transaction_core.py
 */
contract SimpleFlashloan is FlashLoanReceiverBase {
    address public immutable owner;
    
    event FlashLoanExecuted(
        address[] assets,
        uint256[] amounts,
        uint256[] premiums
    );

    error NotOwner();
    error NotPool();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(address _addressProvider) FlashLoanReceiverBase(IPoolAddressesProvider(_addressProvider)) {
        owner = msg.sender;
    }

    /**
     * @notice Initiates a flashloan
     * @param assets The addresses of the assets being flash-borrowed
     * @param amounts The amounts of the assets being flash-borrowed
     * @param params Arbitrary bytes to be passed to executeOperation
     */
    function requestFlashLoan(
        address[] calldata assets,
        uint256[] calldata amounts,
        bytes calldata params
    ) external onlyOwner {
        uint256[] memory modes = new uint256[](assets.length);
        // 0 = no debt, 1 = stable, 2 = variable
        for (uint256 i = 0; i < assets.length; i++) {
            modes[i] = 0;
        }

        POOL.flashLoan(
            address(this),
            assets,
            amounts,
            modes,
            address(this),
            params,
            0
        );
    }

    /**
     * @notice Executes an operation after receiving the flash-borrowed assets
     * @param assets The addresses of the flash-borrowed assets
     * @param amounts The amounts of the flash-borrowed assets
     * @param premiums The premiums (fees) for the flash-borrowed assets
     * @param initiator The address that initiated the flash loan
     * @param params Arbitrary bytes passed to executeOperation
     * @return success Whether the operation was successful
     */
    function executeOperation(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        address initiator,
        bytes calldata params
    ) external override returns (bool) {
        if (msg.sender != address(POOL)) revert NotPool();

        // Approve repayment
        for (uint256 i = 0; i < assets.length; i++) {
            uint256 amountOwed = amounts[i] + premiums[i];
            IERC20(assets[i]).approve(address(POOL), amountOwed);
        }

        emit FlashLoanExecuted(assets, amounts, premiums);
        return true;
    }

    /**
     * @notice Allows the owner to withdraw tokens from the contract
     * @param token The token to withdraw
     * @param amount The amount to withdraw
     */
    function withdrawToken(address token, uint256 amount) external onlyOwner {
        IERC20(token).transfer(owner, amount);
    }

    /**
     * @notice Allows the owner to withdraw ETH from the contract
     */
    function withdrawETH() external onlyOwner {
        payable(owner).transfer(address(this).balance);
    }

    receive() external payable {}
}
